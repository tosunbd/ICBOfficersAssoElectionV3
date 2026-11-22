"""Dashboard router — results JSON and the live Server-Sent-Events stream."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import Ballot, Election
from app.models.admin_user import AdminUser
from app.models.election import ElectionStatus
from app.schemas.dashboard import ActiveElectionResponse, DashboardResponse
from app.services.events import notifier
from app.services.live_replay import live_replay
from app.services.vote_counter import vote_counter
from app.utils.security import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/active", response_model=ActiveElectionResponse)
async def get_active_election(db: AsyncSession = Depends(get_db)):
    """The election the public dashboard should show (active, else the newest)."""
    result = await db.execute(
        select(Election).where(Election.status == ElectionStatus.ACTIVE).order_by(Election.id.desc()).limit(1)
    )
    election = result.scalar_one_or_none()
    if not election:
        result = await db.execute(select(Election).order_by(Election.id.desc()).limit(1))
        election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="No election found")
    data = ActiveElectionResponse.model_validate(election, from_attributes=True)
    data.live_display_seconds = election.ballot_display_seconds
    return data


@router.get("/ballots/{ballot_id}/preview")
async def public_ballot_preview(ballot_id: int, db: AsyncSession = Depends(get_db)):
    """Annotated scan shown on the public live screen (only while results are published)."""
    ballot = (await db.execute(select(Ballot).where(Ballot.id == ballot_id))).scalar_one_or_none()
    if not ballot or not ballot.preview_path or not Path(ballot.preview_path).exists():
        raise HTTPException(status_code=404, detail="No preview")
    election = (await db.execute(select(Election).where(Election.id == ballot.election_id))).scalar_one_or_none()
    if not election or not election.dashboard_published:
        raise HTTPException(status_code=403, detail="Results are not published")
    return FileResponse(ballot.preview_path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/latest/{election_id}")
async def latest_ballot(election_id: int, db: AsyncSession = Depends(get_db)):
    """The last ballot sent to the live screen, so a screen opened (or
    refreshed) mid-count shows it at once.  `null` when there is none yet."""
    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election or not election.dashboard_published or election.dashboard_paused:
        return None
    return notifier.latest("ballot", election_id)


@router.get("/results/{election_id}", response_model=DashboardResponse)
async def get_results(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    user: AdminUser | None = Depends(get_optional_user),
):
    """Current results.  Unpublished results are only returned to admins.

    While the count is replayed after Publish the public gets the totals up
    to the ballot on screen; admins always get the real ones."""
    try:
        if user:
            data = await vote_counter.get_dashboard_data(db, election_id, include_results=True)
        else:
            data = await vote_counter.get_dashboard_data(db, election_id, up_to_ballot_id=live_replay.cursor(election_id))
        data.replay = live_replay.progress(election_id)
        return data
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


async def dashboard_events(election_id: int, is_disconnected=None, after: int | None = None):
    """Async generator behind the SSE endpoint (kept separate so it can be tested).

    Events: `ballot` (one per counted ballot, in order, with the totals after
    it), `update` (full results on every other change and periodically),
    `paused`.  `after` = the id of the last `ballot` event a reconnecting
    screen received: the ballots it missed meanwhile are sent first.
    """
    last_seq = notifier.last_seq  # new viewers do not replay history
    if after is not None and 0 <= after < last_seq:
        last_seq = after
    while True:
        if is_disconnected is not None and await is_disconnected():
            return
        seen_version = notifier.version
        try:
            async with AsyncSessionLocal() as db:
                election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
                if not election:
                    yield {"event": "error", "data": json.dumps({"error": "Election not found"})}
                    return
                if election.dashboard_paused:
                    last_seq = notifier.last_seq  # ballots counted while paused are not replayed
                    yield {"event": "paused", "data": json.dumps({"status": "paused"})}
                else:
                    for seq, kind, payload in notifier.events_after(last_seq):
                        last_seq = seq
                        if kind == "ballot" and payload.get("election_id") == election_id:
                            yield {"event": "ballot", "id": str(seq), "data": json.dumps(payload)}
                    data = await vote_counter.get_dashboard_data(
                        db, election_id, up_to_ballot_id=live_replay.cursor(election_id)
                    )
                    data.replay = live_replay.progress(election_id)
                    yield {"event": "update", "data": data.model_dump_json()}
        except Exception as exc:
            logger.exception("SSE error")
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}

        await notifier.wait_for_change(seen_version, timeout=settings.SSE_REFRESH_INTERVAL)


@router.get("/stream/{election_id}")
async def stream_results(election_id: int, request: Request, after: int | None = Query(None, ge=0)):
    """Server-Sent Events: pushes `update` immediately after every change and
    at least every SSE_REFRESH_INTERVAL seconds; `paused` while the admin has
    paused the dashboard.  `after`: see dashboard_events."""
    return EventSourceResponse(dashboard_events(election_id, request.is_disconnected, after), ping=15)
