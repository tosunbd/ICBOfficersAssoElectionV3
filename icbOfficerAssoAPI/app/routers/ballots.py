"""Ballots router — upload, list, review, reprocess and delete scanned ballots."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Ballot, Candidate, Election, Position, Vote
from app.models.admin_user import AdminUser
from app.models.ballot import BallotStatus
from app.schemas.ballot import (
    BallotDetailResponse, BallotListResponse, BallotResponse, BallotReviewRequest, BulkDeleteRequest,
    BulkDeleteResponse, ProcessFolderResponse,
)
from app.services.ballot_processor import FolderScanBusy, ballot_processor
from app.services.events import notifier
from app.utils import audit
from app.utils.security import get_current_user
from app.utils.time import utcnow

router = APIRouter(prefix="/api/ballots", tags=["Ballots"])

COUNTING_PAUSED_MESSAGE = (
    "Counting is paused by the election commission. Press START on the live screen "
    "to continue; the files wait in the Scanned folder."
)
SCAN_BUSY_MESSAGE = (
    "The Scanned folder is already being read (counting carries on by itself after START). "
    "The ballots appear on the live screen one by one."
)
NO_CANDIDATES_MESSAGE = (
    "This election has no candidates yet. Add them first in Admin -> Candidates "
    "(Import CSV loads the whole list). The scanned files stay in the Scanned folder."
)


async def _get_ballot(db: AsyncSession, ballot_id: int) -> Ballot:
    result = await db.execute(select(Ballot).where(Ballot.id == ballot_id))
    ballot = result.scalar_one_or_none()
    if not ballot:
        raise HTTPException(status_code=404, detail="Ballot not found")
    return ballot


# Also at the bare prefix: a 307 slash-redirect through the UI proxy loses the Authorization header.
@router.get("", response_model=BallotListResponse, include_in_schema=False)
@router.get("/", response_model=BallotListResponse)
async def list_ballots(
    election_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    status_filter: str | None = Query(None, description="processed | needs_review | reviewed | error"),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    query = select(Ballot).where(Ballot.election_id == election_id)
    count_query = select(func.count(Ballot.id)).where(Ballot.election_id == election_id)
    if status_filter:
        query = query.where(Ballot.status == status_filter)
        count_query = count_query.where(Ballot.status == status_filter)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Ballot.id.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return BallotListResponse(
        ballots=[BallotResponse.from_model(b) for b in result.scalars().all()],
        total=total, page=page, per_page=per_page,
    )


@router.get("/{ballot_id}", response_model=BallotDetailResponse)
async def get_ballot(
    ballot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    return BallotDetailResponse.from_model(await _get_ballot(db, ballot_id))


@router.get("/{ballot_id}/preview")
async def get_ballot_preview(
    ballot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Annotated PNG of the scanned page (green = marked box)."""
    ballot = await _get_ballot(db, ballot_id)
    if not ballot.preview_path or not Path(ballot.preview_path).exists():
        raise HTTPException(status_code=404, detail="No preview available for this ballot")
    return FileResponse(ballot.preview_path, media_type="image/png")


@router.get("/{ballot_id}/file")
async def get_ballot_file(
    ballot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """The original scanned file."""
    ballot = await _get_ballot(db, ballot_id)
    path = Path(ballot.completed_path or ballot.original_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Scanned file not found on disk")
    return FileResponse(str(path), filename=path.name)


@router.post("/upload", response_model=list[BallotResponse])
async def upload_ballots(
    election_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Upload scanned files (PDF or image); each is processed immediately."""
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")
    if election.counting_paused:
        raise HTTPException(status_code=409, detail=COUNTING_PAUSED_MESSAGE)
    if not await ballot_processor.candidate_count(db, election_id):
        raise HTTPException(status_code=400, detail=NO_CANDIDATES_MESSAGE)

    scanned_dir = settings.scanned_path
    created: list[Ballot] = []
    for upload in files:
        name = Path(upload.filename or "upload.pdf").name
        if not ballot_processor.is_supported(Path(name)):
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {name}")
        target = scanned_dir / name
        counter = 1
        while target.exists():
            target = scanned_dir / f"{Path(name).stem}_{counter}{Path(name).suffix}"
            counter += 1

        key = str(target.resolve())
        ballot_processor.in_flight.add(key)  # keep the folder watcher away from it
        try:
            target.write_bytes(await upload.read())
            created.extend(await ballot_processor.process_file(db, target, election_id, source="upload"))
        finally:
            ballot_processor.in_flight.discard(key)

    audit.record(db, current_user.id, "ballot_upload", f"{len(files)} file(s) uploaded, {len(created)} ballot(s) created")
    await db.commit()
    return [BallotResponse.from_model(b) for b in created]


@router.post("/scan-folder", response_model=ProcessFolderResponse)
async def process_scanned_folder(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Process every file waiting in the Scanned folder right now."""
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")
    if election.counting_paused:
        raise HTTPException(status_code=409, detail=COUNTING_PAUSED_MESSAGE)
    # Without candidates nothing can be read: refuse, and leave the files where they are
    if not await ballot_processor.candidate_count(db, election_id):
        raise HTTPException(status_code=400, detail=NO_CANDIDATES_MESSAGE)
    try:
        summary = await ballot_processor.process_scanned_folder(db, election_id, source="manual")
    except FolderScanBusy:
        raise HTTPException(status_code=409, detail=SCAN_BUSY_MESSAGE)
    audit.record(
        db, current_user.id, "folder_scan",
        f"Election #{election_id}: {summary['files_processed']} processed, {summary['files_errored']} errors",
    )
    await db.commit()
    return ProcessFolderResponse(**summary)


@router.put("/{ballot_id}/review", response_model=BallotDetailResponse)
async def review_ballot(
    ballot_id: int,
    data: BallotReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Replace the ballot's votes with what the Election Commission confirmed (a manual file).

    Works on every ballot, also a file the scanner could not read: once saved it
    counts in the totals.  A ballot is never rejected as a whole; a vote the
    commission leaves out simply does not count.
    """
    ballot = await _get_ballot(db, ballot_id)

    positions = (await db.execute(
        select(Position).where(Position.election_id == ballot.election_id)
    )).scalars().all()
    max_by_position = {p.id: p.max_selections for p in positions}
    candidates = (await db.execute(
        select(Candidate).where(Candidate.election_id == ballot.election_id)
    )).scalars().all()
    candidate_position = {c.id: c.position_id for c in candidates}

    # Validate the submitted votes against the election's rules
    per_position: dict[int, int] = {}
    for vote in data.votes:
        if candidate_position.get(vote.candidate_id) != vote.position_id:
            raise HTTPException(status_code=400, detail=f"Candidate {vote.candidate_id} is not in position {vote.position_id}")
        if vote.is_valid:
            per_position[vote.position_id] = per_position.get(vote.position_id, 0) + 1
    for position_id, count in per_position.items():
        if count > max_by_position.get(position_id, 1):
            raise HTTPException(
                status_code=400,
                detail=f"Position {position_id} allows at most {max_by_position.get(position_id, 1)} vote(s)",
            )

    await ballot_processor.remove_votes(db, ballot)
    counted = 0
    for vote in data.votes:
        valid = vote.is_valid
        db.add(Vote(
            ballot_id=ballot_id, candidate_id=vote.candidate_id, position_id=vote.position_id,
            is_valid=valid, invalid_reason=None if valid else "Not counted by the committee", confidence_score=1.0,
        ))
        if valid:
            counted += 1
            await db.execute(
                update(Candidate).where(Candidate.id == vote.candidate_id)
                .values(vote_count=Candidate.vote_count + 1)
            )

    ballot.status = BallotStatus.REVIEWED
    ballot.reviewed_at = utcnow()
    ballot.is_valid = True
    ballot.total_votes_extracted = counted
    ballot.error_message = None
    if data.ballot_paper_no is not None and (data.ballot_paper_no or None) != ballot.ballot_paper_no:
        ballot.ballot_paper_no = data.ballot_paper_no.strip() or None
        ballot_processor.rename_completed_file(ballot)

    audit.record(
        db, current_user.id, "ballot_review",
        f"Ballot #{ballot_id} reviewed by {current_user.username}: {counted} valid vote(s)",
    )
    await db.commit()
    db.expire_all()
    reviewed = await _get_ballot(db, ballot_id)
    await ballot_processor.publish_live_event(db, reviewed, kind="reviewed")  # corrections are shown publicly too
    notifier.notify()
    return BallotDetailResponse.from_model(reviewed)


@router.post("/{ballot_id}/reprocess", response_model=BallotDetailResponse)
async def reprocess_ballot(
    ballot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Run mark detection again on the stored scan."""
    ballot = await _get_ballot(db, ballot_id)
    try:
        await ballot_processor.reprocess_ballot(db, ballot)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record(db, current_user.id, "ballot_reprocess", f"Ballot #{ballot_id} reprocessed -> {ballot.status}")
    await db.commit()
    db.expire_all()
    return BallotDetailResponse.from_model(await _get_ballot(db, ballot_id))


@router.delete("/{ballot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ballot(
    ballot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Remove a ballot and its votes (the scanned file stays in Completed)."""
    ballot = await _get_ballot(db, ballot_id)
    await _delete_ballot(db, ballot, current_user)
    await db.commit()
    notifier.notify()


async def _delete_ballot(db: AsyncSession, ballot: Ballot, user: AdminUser) -> None:
    await ballot_processor.remove_votes(db, ballot)
    if ballot.preview_path:
        Path(ballot.preview_path).unlink(missing_ok=True)
    audit.record(db, user.id, "ballot_delete", f"Ballot #{ballot.id} ({ballot.pdf_filename}) deleted")
    await db.delete(ballot)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_ballots(
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Delete several ballots at once: the given ids, or every ballot of an
    election (optionally only those with one status)."""
    query = select(Ballot)
    if body.ballot_ids:
        query = query.where(Ballot.id.in_(body.ballot_ids))
    elif body.all_matching and body.election_id:
        query = query.where(Ballot.election_id == body.election_id)
        if body.status_filter:
            query = query.where(Ballot.status == body.status_filter)
    else:
        raise HTTPException(status_code=400, detail="Give ballot_ids, or election_id with all_matching=true")

    ballots = (await db.execute(query)).scalars().all()
    for ballot in ballots:
        await _delete_ballot(db, ballot, current_user)
    await db.commit()
    notifier.notify()
    return BulkDeleteResponse(deleted=len(ballots))
