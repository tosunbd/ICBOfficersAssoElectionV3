"""Ballot processor — turns a scanned file into vote records.

Flow for one file:
    render pages -> detect marks -> validate -> insert votes -> update counts
    -> save preview -> move file to Completed (or Failed) -> notify dashboards

Validation rules (mirrors the printed instructions on the ballot):
* a position with more marks than `max_selections` is an over-vote: those
  marks are stored but flagged invalid and are NOT counted;
* a page whose detected boxes do not match the expected layout, or with
  low-confidence marks, is counted but flagged `needs_review`.

Only one file is processed at a time (asyncio lock) so the folder watcher,
manual uploads and the "scan folder" button can never double-process a file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Ballot, Candidate, Election, Position, Vote
from app.models.ballot import BallotStatus
from app.services.events import notifier
from app.services.ocr_service import SUPPORTED_SUFFIXES, PageResult, ocr_service
from app.services.vote_counter import vote_counter
from app.utils import audit, paper_number
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class FolderScanBusy(Exception):
    """The Scanned folder is already being worked through for this election."""


class BallotProcessor:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.in_flight: set[str] = set()  # absolute paths currently being handled
        self._folder_scans: set[int] = set()  # elections whose Scanned folder is being worked through
        self._resume_tasks: dict[int, asyncio.Task] = {}

    # ------------------------------------------------------------ layout
    async def build_layout(self, db: AsyncSession, election_id: int) -> tuple[list[dict], dict[int, int]]:
        """Expected box grid for the election.

        Returns (layout, max_selections_by_position).  Candidates are laid out
        in ballot order: positions by `position_order`, candidates by
        `display_order`, `BALLOT_COLUMNS` per row.
        """
        result = await db.execute(
            select(Candidate, Position)
            .join(Position, Candidate.position_id == Position.id)
            .where(Candidate.election_id == election_id)
            .order_by(Position.position_order, Candidate.display_order, Candidate.id)
        )
        rows = result.all()
        columns = max(1, settings.BALLOT_COLUMNS)

        layout: list[dict] = []
        max_by_position: dict[int, int] = {}
        row_index = -1
        current_position = None
        slot = 0
        for candidate, position in rows:
            if position.id != current_position:
                current_position = position.id
                max_by_position[position.id] = position.max_selections
                row_index += 1
                slot = 0
            elif slot == columns:
                row_index += 1
                slot = 0
            layout.append({
                "candidate_id": candidate.id,
                "position_id": position.id,
                "voter_no": candidate.voter_no,
                "row_index": row_index,
                "col_index": slot,
            })
            slot += 1
        return layout, max_by_position

    @staticmethod
    async def candidate_count(db: AsyncSession, election_id: int) -> int:
        return (await db.execute(
            select(func.count(Candidate.id)).where(Candidate.election_id == election_id)
        )).scalar() or 0

    # ------------------------------------------------------------ public
    @staticmethod
    async def counting_paused(db: AsyncSession, election_id: int) -> bool:
        """True while the election commission has paused the count (PAUSE on the live screen)."""
        paused = await db.scalar(select(Election.counting_paused).where(Election.id == election_id))
        return bool(paused)

    @staticmethod
    def is_supported(path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_SUFFIXES

    async def process_file(
        self, db: AsyncSession, path: Path, election_id: int, source: str = "watcher"
    ) -> list[Ballot]:
        """Process every page of `path`.  Returns the created ballot records.

        Never raises for problems with the file itself: those become ballots
        with status `error`.  The file is always moved out of the Scanned
        folder afterwards (Completed on success, Failed otherwise).
        """
        path = Path(path)
        key = str(path.resolve())
        self.in_flight.add(key)
        try:
            async with self._lock:
                if not path.exists():
                    logger.info("Skipping %s: file no longer exists", path.name)
                    return []
                return await self._process_locked(db, path, election_id, source)
        finally:
            self.in_flight.discard(key)

    async def _process_locked(self, db: AsyncSession, path: Path, election_id: int, source: str) -> list[Ballot]:
        layout, max_by_position = await self.build_layout(db, election_id)
        ballots: list[Ballot] = []

        if not layout:
            return [await self._fail(db, path, election_id, source, "No candidates defined for this election")]

        try:
            page_results: list[PageResult] = await asyncio.to_thread(ocr_service.process_file, path, layout)
        except Exception as exc:  # unreadable / corrupt file
            logger.exception("Could not read %s", path.name)
            return [await self._fail(db, path, election_id, source, f"Could not read file: {exc}")]

        for page_no, page in enumerate(page_results, start=1):
            ballot = Ballot(
                election_id=election_id,
                pdf_filename=path.name,
                page_number=page_no,
                source=source,
                original_path=str(path),
                status=BallotStatus.PROCESSING,
                scanned_at=utcnow(),
            )
            db.add(ballot)
            await db.flush()
            await self._store_page(db, ballot, page, max_by_position)
            ballots.append(ballot)

        first_no = await self._next_paper_no(db, election_id)
        for offset, ballot in enumerate(ballots):
            ballot.ballot_paper_no = self.format_paper_no(first_no + offset)
        await db.commit()

        new_name = self.completed_file_name(ballots, path.suffix)
        dest = self._move(path, settings.completed_path, new_name)
        for ballot in ballots:
            ballot.completed_path = str(dest) if dest else None
            if dest:
                ballot.pdf_filename = dest.name
            preview = settings.preview_path / f"ballot_{ballot.id}.png"
            page = page_results[ballot.page_number - 1]
            try:
                await asyncio.to_thread(ocr_service.render_preview, page, preview)
                ballot.preview_path = str(preview)
            except Exception:  # preview is optional
                logger.warning("Preview could not be written for ballot %s", ballot.id)
        await db.commit()
        for ballot in ballots:
            await self.publish_live_event(db, ballot)
        notifier.notify()

        logger.info(
            "Processed %s (%d page(s), source=%s): %s",
            path.name, len(ballots), source, ", ".join(f"#{b.id} {b.status}" for b in ballots),
        )
        return ballots

    async def _store_page(self, db: AsyncSession, ballot: Ballot, page: PageResult, max_by_position: dict[int, int]) -> None:
        """Insert votes for one page and apply the validation rules."""
        warnings = list(page.warnings)
        marks_by_position: dict[int, list] = {}
        void_marks = 0
        for mark in page.marks:
            if mark.is_marked:
                marks_by_position.setdefault(mark.position_id, []).append(mark)
                if mark.void_reason:
                    void_marks += 1
                    warnings.append(f"Candidate {mark.candidate_id}: {mark.void_reason}")

        # Rule (ka): one X per candidate, at most `max_selections` per post.
        # Marks already void by rules (kha)/(ga) do not count towards the limit.
        over_voted: set[int] = set()
        for position_id, marks in marks_by_position.items():
            usable = [m for m in marks if not m.void_reason]
            if len(usable) > max_by_position.get(position_id, 1):
                over_voted.add(position_id)
                warnings.append(
                    f"Rule (ka): position {position_id} has {len(usable)} marks but only "
                    f"{max_by_position.get(position_id, 1)} allowed (votes not counted)"
                )

        low_confidence = any(
            m.confidence < settings.LOW_CONFIDENCE_THRESHOLD for m in page.marks if m.box is not None
        )

        counted = 0
        for position_id, marks in marks_by_position.items():
            for mark in marks:
                reason = mark.void_reason
                if reason is None and position_id in over_voted:
                    reason = "Rule (ka): more marks than allowed for this post"
                db.add(Vote(
                    ballot_id=ballot.id,
                    candidate_id=mark.candidate_id,
                    position_id=position_id,
                    is_valid=reason is None,
                    invalid_reason=reason,
                    confidence_score=mark.confidence,
                ))
                if reason is None:
                    counted += 1
                    await db.execute(
                        update(Candidate)
                        .where(Candidate.id == mark.candidate_id)
                        .values(vote_count=Candidate.vote_count + 1)
                    )

        ballot.printed_paper_no = await asyncio.to_thread(paper_number.read_paper_no, page.image)
        number_flag = self._check_file_number(ballot, warnings)
        needs_review = (not page.layout_ok) or bool(over_voted) or low_confidence or void_marks > 0 or number_flag
        ballot.status = BallotStatus.NEEDS_REVIEW if needs_review else BallotStatus.PROCESSED
        ballot.total_votes_extracted = counted
        ballot.boxes_detected = page.boxes_detected
        ballot.boxes_expected = page.boxes_expected
        ballot.ocr_warnings = json.dumps(warnings) if warnings else None
        ballot.processed_at = utcnow()

    @staticmethod
    def _file_paper_no(ballot: Ballot) -> str | None:
        # the name as scanned: the Completed copy is renamed Ballot_<no> afterwards
        return paper_number.file_paper_no(Path(ballot.original_path or ballot.pdf_filename).name)

    def _check_file_number(self, ballot: Ballot, warnings: list[str]) -> bool:
        """A scan named img_<no>.jpg must be the paper whose number is printed or stamped
        in the box at the top right (same number; leading zeros do not count).
        Returns True (needs review) when they differ or the number cannot be read."""
        expected = self._file_paper_no(ballot)
        if expected is None:
            return False
        name = Path(ballot.original_path or ballot.pdf_filename).name
        if not ballot.printed_paper_no:
            warnings.append(f"File number: {name} says paper {expected}, but the paper number could not be read from the ballot")
            return True
        if not paper_number.same_paper(expected, ballot.printed_paper_no):
            warnings.append(
                f"File number: MISMATCH - {name} says paper {expected}, the ballot is paper {ballot.printed_paper_no}"
            )
            return True
        return False

    # ---------------------------------------------------------- reprocess
    async def reprocess_ballot(self, db: AsyncSession, ballot: Ballot) -> Ballot:
        """Run detection again for an existing ballot (same id, votes replaced)."""
        source_path = Path(ballot.completed_path or ballot.original_path or "")
        if not source_path.exists():
            raise FileNotFoundError("The scanned file for this ballot no longer exists")

        layout, max_by_position = await self.build_layout(db, ballot.election_id)
        if not layout:
            raise ValueError("No candidates defined for this election")

        await self.remove_votes(db, ballot)
        pages = await asyncio.to_thread(ocr_service.process_file, source_path, layout)
        index = min(ballot.page_number, len(pages)) - 1
        page = pages[index]
        await self._store_page(db, ballot, page, max_by_position)
        ballot.reviewed_at = None
        ballot.error_message = None
        await db.commit()

        preview = settings.preview_path / f"ballot_{ballot.id}.png"
        await asyncio.to_thread(ocr_service.render_preview, page, preview)
        ballot.preview_path = str(preview)
        await db.commit()
        await self.publish_live_event(db, ballot, kind="reread")
        notifier.notify()
        return ballot

    async def _fail(self, db: AsyncSession, path: Path, election_id: int, source: str, message: str) -> Ballot:
        """Record a file that could not be counted, move it to Failed and still
        show it on the live screen (with the page itself whenever it renders)."""
        ballot = self._error_ballot(path, election_id, source, message)
        db.add(ballot)
        await db.commit()
        preview = settings.preview_path / f"ballot_{ballot.id}.png"
        try:
            if await asyncio.to_thread(ocr_service.render_raw_preview, path, preview):
                ballot.preview_path = str(preview)
        except Exception:  # a corrupt file has no picture to show
            logger.info("No preview for unreadable file %s", path.name)
        dest = self._move(path, settings.failed_path)
        ballot.completed_path = str(dest) if dest else None
        await db.commit()
        await self.publish_live_event(db, ballot, kind="unreadable")
        notifier.notify()
        return ballot

    async def publish_live_event(self, db: AsyncSession, ballot: Ballot, kind: str = "counted") -> None:
        """Send this ballot (votes + totals after it) to the public live screen.

        Every scanned file is shown — counted, re-read, corrected by the
        committee or unreadable — so the audience sees all of it.  While the
        count is being replayed after Publish nothing is sent: the replay
        reaches this ballot in its turn."""
        from app.services.live_replay import live_replay

        if live_replay.is_running(ballot.election_id):
            return
        try:
            counted = (await db.execute(
                select(func.count(Ballot.id)).where(
                    Ballot.election_id == ballot.election_id, Ballot.status.in_(BallotStatus.COUNTED)
                )
            )).scalar() or 0
            results = await vote_counter.get_dashboard_data(db, ballot.election_id)
            election = await db.get(Election, ballot.election_id)  # refreshed by get_dashboard_data just above
            event = await self.build_live_event(
                db, ballot, kind=kind, sequence_no=counted, results=results,
                display_seconds=election.ballot_display_seconds if election else settings.LIVE_BALLOT_DISPLAY_SECONDS,
            )
            notifier.publish("ballot", event.model_dump(mode="json"))
        except Exception:  # the live screen is a nicety; never break counting for it
            logger.exception("Could not publish live event for ballot %s", ballot.id)

    @staticmethod
    async def build_live_event(
        db: AsyncSession, ballot: Ballot, *, kind: str, sequence_no: int, results, display_seconds: int, replay=None,
    ):
        """The public-screen payload for one ballot: its votes plus `results`."""
        from app.schemas.dashboard import LiveBallotEvent, LiveVote

        rows = (await db.execute(
            select(Vote, Candidate, Position)
            .join(Candidate, Vote.candidate_id == Candidate.id)
            .join(Position, Vote.position_id == Position.id)
            .where(Vote.ballot_id == ballot.id)
            .order_by(Position.position_order, Candidate.display_order)
        )).all()
        votes = [LiveVote(
            position_id=position.id, position_order=position.position_order,
            position_name_en=position.name_en, position_name_bn=position.name_bn,
            candidate_id=candidate.id, voter_no=candidate.voter_no,
            candidate_name_en=candidate.name_en, candidate_name_bn=candidate.name_bn,
            is_valid=vote.is_valid, invalid_reason=vote.invalid_reason, confidence=vote.confidence_score,
        ) for vote, candidate, position in rows]
        return LiveBallotEvent(
            ballot_id=ballot.id, election_id=ballot.election_id, sequence_no=sequence_no,
            ballot_paper_no=ballot.ballot_paper_no, pdf_filename=ballot.pdf_filename,
            page_number=ballot.page_number, status=ballot.status,
            kind=kind, error_message=ballot.error_message, is_valid=ballot.is_valid is not False,
            has_preview=bool(ballot.preview_path), votes=votes,
            display_seconds=display_seconds, results=results, replay=replay,
        )

    async def remove_votes(self, db: AsyncSession, ballot: Ballot) -> None:
        """Delete a ballot's votes and roll back the candidate counters."""
        result = await db.execute(select(Vote).where(Vote.ballot_id == ballot.id))
        for vote in result.scalars().all():
            if vote.is_valid:
                await db.execute(
                    update(Candidate)
                    .where(Candidate.id == vote.candidate_id)
                    .values(vote_count=Candidate.vote_count - 1)
                )
            await db.delete(vote)
        await db.flush()
        await db.refresh(ballot, attribute_names=["votes"])  # drop the stale collection

    # -------------------------------------------------------------- folder
    def waiting_files(self) -> list[Path]:
        """Supported files in the Scanned folder that nobody is handling yet, in name order."""
        return sorted(
            p for p in settings.scanned_path.iterdir()
            if p.is_file() and self.is_supported(p) and str(p.resolve()) not in self.in_flight
        )

    def folder_scan_running(self, election_id: int) -> bool:
        return election_id in self._folder_scans

    async def process_scanned_folder(self, db: AsyncSession, election_id: int, source: str = "manual") -> dict:
        """Process every supported file currently in the Scanned folder.

        Raises FolderScanBusy when the folder is already being worked through
        (an earlier Scan, or the scan START resumed after a PAUSE)."""
        if election_id in self._folder_scans:
            raise FolderScanBusy()
        self._folder_scans.add(election_id)
        try:
            return await self._scan_folder(db, election_id, source)
        finally:
            self._folder_scans.discard(election_id)

    def resume_folder_scan(self, election_id: int) -> bool:
        """START after a PAUSE: carry on with the files waiting in the Scanned
        folder, exactly as if Scan had been pressed again.  False when there is
        nothing to resume (no files, or a scan is still running)."""
        if election_id in self._folder_scans or not self.waiting_files():
            return False
        self._folder_scans.add(election_id)  # claimed at once: a second START or Scan cannot start another
        self._resume_tasks[election_id] = asyncio.create_task(
            self._resume(election_id), name=f"resume-folder-scan-{election_id}"
        )
        return True

    async def wait_for_resumed_scan(self, election_id: int) -> None:
        task = self._resume_tasks.get(election_id)
        if task:
            await task

    async def _resume(self, election_id: int) -> None:
        from app.database import AsyncSessionLocal  # re-bound in place when the year's database changes

        try:
            async with AsyncSessionLocal() as db:
                if not await self.candidate_count(db, election_id):
                    return
                summary = await self._scan_folder(db, election_id, source="manual")
                audit.record(
                    db, None, "folder_scan",
                    f"Election #{election_id}: resumed after START, "
                    f"{summary['files_processed']} processed, {summary['files_errored']} errors",
                )
                await db.commit()
        except Exception:
            logger.exception("Resumed folder scan failed for election %s", election_id)
        finally:
            self._folder_scans.discard(election_id)
            self._resume_tasks.pop(election_id, None)

    async def _scan_folder(self, db: AsyncSession, election_id: int, source: str) -> dict:
        files = self.waiting_files()
        summary = {"files_found": len(files), "files_processed": 0, "files_errored": 0, "details": [], "paused": False}
        for index, path in enumerate(files):
            if index and settings.PROCESS_DELAY_SECONDS > 0:
                await asyncio.sleep(settings.PROCESS_DELAY_SECONDS)
            if await self.counting_paused(db, election_id):
                summary["paused"] = True  # PAUSE pressed: the rest wait in the Scanned folder
                break
            ballots = await self.process_file(db, path, election_id, source=source)
            errored = any(b.status == BallotStatus.ERROR for b in ballots)
            summary["files_errored" if errored else "files_processed"] += 1
            summary["details"].append({
                "filename": path.name,
                "status": "error" if errored else "processed",
                "ballot_ids": [b.id for b in ballots],
                "votes_extracted": sum(b.total_votes_extracted for b in ballots),
                "error": next((b.error_message for b in ballots if b.error_message), None),
            })
        logger.info(
            "Folder scan: %d processed, %d errors, %d files",
            summary["files_processed"], summary["files_errored"], summary["files_found"],
        )
        return summary

    async def recount_votes(self, db: AsyncSession, election_id: int) -> None:
        """Rebuild the denormalised counters from the vote records."""
        await db.execute(
            update(Candidate).where(Candidate.election_id == election_id).values(vote_count=0)
        )
        result = await db.execute(
            select(Vote.candidate_id, func.count(Vote.id))
            .join(Ballot, Vote.ballot_id == Ballot.id)
            .where(Ballot.election_id == election_id, Vote.is_valid.is_(True), Ballot.is_valid.is_(True))
            .group_by(Vote.candidate_id)
        )
        for candidate_id, count in result.all():
            await db.execute(
                update(Candidate).where(Candidate.id == candidate_id).values(vote_count=count)
            )
        await db.commit()
        notifier.notify()
        logger.info("Recount completed for election %s", election_id)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def format_paper_no(number: int) -> str:
        return str(number).zfill(settings.BALLOT_NUMBER_DIGITS)

    @staticmethod
    async def _next_paper_no(db: AsyncSession, election_id: int) -> int:
        """1 + the highest numeric ballot paper number already used in this election."""
        result = await db.execute(
            select(Ballot.ballot_paper_no).where(Ballot.election_id == election_id, Ballot.ballot_paper_no.is_not(None))
        )
        highest = 0
        for value in result.scalars().all():
            digits = "".join(ch for ch in str(value) if ch.isdigit())
            if digits:
                highest = max(highest, int(digits))
        return highest + 1

    @staticmethod
    def completed_file_name(ballots: list[Ballot], suffix: str) -> str:
        """Ballot_0001.pdf for one page, Ballot_0011-0020.pdf for a batch."""
        numbers = [b.ballot_paper_no for b in ballots if b.ballot_paper_no]
        if not numbers:
            return ""
        label = numbers[0] if len(numbers) == 1 else f"{numbers[0]}-{numbers[-1]}"
        return f"Ballot_{label}{suffix.lower() if suffix else '.pdf'}"

    def rename_completed_file(self, ballot: Ballot) -> None:
        """Keep the file name in step with the ballot paper number (single-page files)."""
        if not ballot.completed_path or not ballot.ballot_paper_no:
            return
        current = Path(ballot.completed_path)
        if not current.exists() or ballot.page_number != 1:
            return
        wanted = self.completed_file_name([ballot], current.suffix)
        if not wanted or current.name == wanted:
            return
        target = current.with_name(wanted)
        counter = 1
        while target.exists():
            target = current.with_name(f"{Path(wanted).stem}_{counter}{current.suffix}")
            counter += 1
        try:
            current.rename(target)
            ballot.completed_path = str(target)
            ballot.pdf_filename = target.name
        except OSError:
            logger.warning("Could not rename %s to %s", current.name, target.name)

    @staticmethod
    def _error_ballot(path: Path, election_id: int, source: str, message: str) -> Ballot:
        return Ballot(
            election_id=election_id,
            pdf_filename=path.name,
            page_number=1,
            source=source,
            original_path=str(path),
            status=BallotStatus.ERROR,
            error_message=message,
            processed_at=utcnow(),
        )

    @staticmethod
    def _move(path: Path, folder: Path, new_name: str = "") -> Path | None:
        """Move `path` into `folder` (optionally renamed), never overwriting an existing file."""
        name = new_name or path.name
        dest = folder / name
        counter = 1
        while dest.exists():
            dest = folder / f"{Path(name).stem}_{counter}{Path(name).suffix}"
            counter += 1
        try:
            shutil.move(str(path), str(dest))
            return dest
        except Exception:
            logger.exception("Could not move %s to %s", path.name, folder)
            return None


ballot_processor = BallotProcessor()
