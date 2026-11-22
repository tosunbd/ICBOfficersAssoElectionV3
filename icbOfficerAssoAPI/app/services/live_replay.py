"""Publish replay — the count is shown again, ballot by ballot, when the
committee publishes the results.

Ballots are usually counted before the results are made public.  When the
committee presses Publish, the public screen starts from zero and shows every
scanned file in the order it was scanned (oldest first), each for the
election's `ballot_display_seconds` (set in Admin -> Elections), with the
standings as they stood after that ballot.
So the audience watches the totals grow: a candidate marked on ballots 1 and 3
shows 1, 1, 2.

While a replay runs:
* the public results (`/results`, the SSE `update`) are the totals up to the
  ballot on screen, not the final ones (admins still see the real numbers);
* ballots counted meanwhile are not sent live — the replay reaches them in turn;
* a paused dashboard holds the replay where it is.

When the last ballot has had its time, the replay ends and the screen carries
on with the real totals and the normal live feed.  State lives in memory: a
restart of the API ends the replay (the screen then shows the final totals).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app import database
from app.config import settings
from app.models import Ballot, Election
from app.models.ballot import BallotStatus
from app.schemas.dashboard import ReplayProgress
from app.services.events import notifier
from app.services.vote_counter import vote_counter

logger = logging.getLogger(__name__)

SHOWN = (*BallotStatus.COUNTED, BallotStatus.ERROR)  # every scanned file the audience sees


@dataclass
class _Run:
    election_id: int
    seconds: int
    cursor: int = 0       # id of the last ballot shown; 0 = none yet (all totals are zero)
    shown: int = 0        # files shown so far
    total: int = 0        # files to show (grows if more are counted during the replay)
    task: asyncio.Task | None = field(default=None, repr=False)


class LiveReplay:
    def __init__(self) -> None:
        self._runs: dict[int, _Run] = {}

    # ------------------------------------------------------------- queries
    def is_running(self, election_id: int) -> bool:
        return election_id in self._runs

    def cursor(self, election_id: int) -> int | None:
        """Last ballot id the public totals include, or None when no replay runs."""
        run = self._runs.get(election_id)
        return run.cursor if run else None

    def progress(self, election_id: int) -> ReplayProgress | None:
        run = self._runs.get(election_id)
        return ReplayProgress(position=run.shown, total=run.total) if run else None

    def status(self, election_id: int) -> dict:
        run = self._runs.get(election_id)
        if not run:
            return {"running": False, "shown": 0, "total": 0, "seconds": 0}
        return {"running": True, "shown": run.shown, "total": run.total, "seconds": run.seconds}

    # ------------------------------------------------------------ control
    def start(self, election_id: int, seconds: int, background: bool = True) -> bool:
        """Begin (or restart) the replay, `seconds` per ballot.  False when
        replays are switched off."""
        self.stop(election_id, notify=False)
        if not settings.PUBLISH_REPLAY_ENABLED:
            return False
        run = _Run(election_id=election_id, seconds=max(1, seconds))
        self._runs[election_id] = run
        if background:
            run.task = asyncio.create_task(self._loop(run), name=f"publish-replay-{election_id}")
        notifier.notify()  # screens drop to the zero totals at once
        logger.info("Publish replay started for election %s (%ss per ballot)", election_id, run.seconds)
        return True

    def stop(self, election_id: int, notify: bool = True) -> None:
        """End the replay; the screen jumps to the real totals."""
        run = self._runs.pop(election_id, None)
        if run is None:
            return
        if run.task and run.task is not asyncio.current_task():
            run.task.cancel()
        if notify:
            notifier.notify()
        logger.info("Publish replay ended for election %s after %s of %s ballot(s)", election_id, run.shown, run.total)

    def stop_all(self) -> None:
        for election_id in list(self._runs):
            self.stop(election_id)

    # ---------------------------------------------------------- stepping
    async def advance(self, election_id: int) -> bool | None:
        """Show the next ballot.  True = shown, False = nothing left,
        None = held (dashboard or counting paused) or no replay / election gone."""
        run = self._runs.get(election_id)
        if run is None:
            return None
        async with database.AsyncSessionLocal() as db:
            election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
            if not election or not election.dashboard_published:
                return False
            if election.dashboard_paused or election.counting_paused:
                return None
            run.seconds = max(1, election.ballot_display_seconds)  # a change in Admin applies from the next ballot

            run.total = run.shown + ((await db.execute(
                select(func.count(Ballot.id))
                .where(Ballot.election_id == election_id, Ballot.id > run.cursor, Ballot.status.in_(SHOWN))
            )).scalar() or 0)
            ballot = (await db.execute(
                select(Ballot)
                .where(Ballot.election_id == election_id, Ballot.id > run.cursor, Ballot.status.in_(SHOWN))
                .order_by(Ballot.id)
                .limit(1)
            )).scalar_one_or_none()
            if ballot is None:
                return False

            run.cursor = ballot.id
            run.shown += 1
            counted = (await db.execute(
                select(func.count(Ballot.id)).where(
                    Ballot.election_id == election_id, Ballot.id <= ballot.id, Ballot.status.in_(BallotStatus.COUNTED)
                )
            )).scalar() or 0
            results = await vote_counter.get_dashboard_data(db, election_id, up_to_ballot_id=ballot.id)
            results.replay = ReplayProgress(position=run.shown, total=run.total)

            from app.services.ballot_processor import ballot_processor  # avoids a circular import
            event = await ballot_processor.build_live_event(
                db, ballot,
                kind="unreadable" if ballot.status == BallotStatus.ERROR else "counted",
                sequence_no=counted, results=results, display_seconds=run.seconds,
                replay=results.replay,
            )
        notifier.publish("ballot", event.model_dump(mode="json"))
        return True

    async def _loop(self, run: _Run) -> None:
        try:
            while self._runs.get(run.election_id) is run:
                shown = await self.advance(run.election_id)
                if shown is False:
                    break
                if shown is None:  # paused: check again shortly, the hold restarts on resume
                    await notifier.wait_for_change(notifier.version, timeout=2)
                    continue
                await asyncio.sleep(run.seconds)  # the ballot's time on screen
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Publish replay failed for election %s", run.election_id)
        if self._runs.get(run.election_id) is run:
            self.stop(run.election_id)


live_replay = LiveReplay()
