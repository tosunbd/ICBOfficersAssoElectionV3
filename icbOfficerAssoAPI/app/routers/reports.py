"""Reports router — the data behind the printable result sheets (Admin -> Reports).

Both reports are built from the stored votes in one pass, so the per-candidate
totals of the summary are, by construction, the column sums of the ballot
tally: a vote counts when its ballot is counted (processed / needs review /
reviewed) and the mark itself is valid.  A whole ballot is never rejected; a
mark that breaks the rules (1 to 15) is simply not counted.

"Manual files" are the ballots whose selections the Election Commission saved
on the review screen (status reviewed): files the scanner could not read or
counted wrongly.  They count in the totals like every other ballot.

The same response feeds the Panel Votes report (every candidate carries the
side of the ballot paper it is printed on) and the Null Votes report (every
mark that is not counted, with its reason, and the files not read at all).
"""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AdminUser, Ballot, Election, Position
from app.models.ballot import BallotStatus
from app.schemas.report import (
    ElectionReport, ReportBallot, ReportCandidate, ReportPosition, ReportUnreadFile, ReportVoidMark,
)
from app.services.vote_counter import vote_counter
from app.utils.security import get_current_user
from app.utils.time import utcnow

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/{election_id}", response_model=ElectionReport)
async def election_report(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Result summary (winner of every post) and the ballot-by-ballot 1/0 tally."""
    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")

    positions = (await db.execute(
        select(Position).where(Position.election_id == election_id).order_by(Position.position_order)
    )).scalars().all()
    ballots = (await db.execute(
        select(Ballot)
        .where(Ballot.election_id == election_id, Ballot.status.in_(BallotStatus.COUNTED))
        .order_by(Ballot.id)
    )).scalars().all()

    votes_for: dict[int, int] = defaultdict(int)
    report_ballots: list[ReportBallot] = []
    total_void = 0
    for serial, ballot in enumerate(ballots, start=1):
        counted = sorted({v.candidate_id for v in ballot.votes if v.is_valid}) if ballot.is_valid else []
        void = [
            ReportVoidMark(
                candidate_id=v.candidate_id, position_id=v.position_id,
                reason=(v.invalid_reason or "Not counted") if not v.is_valid else WHOLE_BALLOT_REJECTED,
            )
            for v in sorted(ballot.votes, key=lambda v: v.id)
            if not (v.is_valid and ballot.is_valid)
        ]
        total_void += len(void)
        for candidate_id in counted:
            votes_for[candidate_id] += 1
        report_ballots.append(ReportBallot(
            ballot_id=ballot.id, serial=serial, ballot_paper_no=ballot.ballot_paper_no,
            pdf_filename=ballot.pdf_filename, page_number=ballot.page_number, status=ballot.status,
            is_valid=ballot.is_valid, candidate_ids=counted, void_marks=len(void), void=void,
        ))

    unread = (await db.execute(
        select(Ballot)
        .where(Ballot.election_id == election_id, Ballot.status == BallotStatus.ERROR)
        .order_by(Ballot.id)
    )).scalars().all()

    report_positions = [_rank_position(p, votes_for, len(ballots)) for p in positions]

    return ElectionReport(
        election_id=election.id,
        title=election.title,
        title_bn=election.title_bn,
        year=election.year,
        status=election.status,
        total_voters=election.total_voters,
        generated_at=utcnow(),
        stats=await vote_counter.get_stats(db, election),
        manual_ballots=sum(1 for b in ballots if b.status == BallotStatus.REVIEWED),
        total_votes=sum(votes_for.values()),
        void_marks=total_void,
        positions=report_positions,
        ballots=report_ballots,
        unread_files=[
            ReportUnreadFile(
                ballot_id=b.id, pdf_filename=b.pdf_filename, page_number=b.page_number,
                reason=b.error_message or "The file could not be read",
            )
            for b in unread
        ],
    )


WHOLE_BALLOT_REJECTED = "Whole ballot rejected"  # only on ballots voided before that option was removed


def _panels(position: Position) -> dict[int, str]:
    """Side of the ballot paper each candidate is printed on.

    The ballot prints the candidates of a post two to a row in `display_order`
    (the same layout the reader uses), so they alternate left, right, left ...
    A ballot with another number of columns has no left/right panel.
    """
    if settings.BALLOT_COLUMNS != 2:
        return {}
    ordered = sorted(position.candidates, key=lambda c: (c.display_order, c.id))
    return {c.id: "left" if index % 2 == 0 else "right" for index, c in enumerate(ordered)}


def _rank_position(position: Position, votes_for: dict[int, int], counted_ballots: int) -> ReportPosition:
    """Rank the candidates of one post and mark who is elected.

    The top `max_selections` with at least one vote are elected; when a tie
    straddles the last seat, every candidate in that tie is marked "tie" so the
    committee can decide (nobody in it is declared elected).
    """
    candidates = sorted(position.candidates, key=lambda c: (-votes_for[c.id], c.display_order, c.id))
    ranks: list[int] = []
    previous, rank = None, 0
    for index, candidate in enumerate(candidates, start=1):
        if votes_for[candidate.id] != previous:
            rank, previous = index, votes_for[candidate.id]
        ranks.append(rank)

    panels = _panels(position)
    seats = position.max_selections
    outcomes = [""] * len(candidates)
    if seats < len(candidates) and candidates:
        cutoff_votes = votes_for[candidates[seats - 1].id]
        boundary_tie = votes_for[candidates[seats].id] == cutoff_votes
    else:
        cutoff_votes, boundary_tie = None, False
    for i, candidate in enumerate(candidates[:seats]):
        votes = votes_for[candidate.id]
        if votes == 0:
            continue
        outcomes[i] = "tie" if boundary_tie and votes == cutoff_votes else "elected"
    if boundary_tie and cutoff_votes:
        for i in range(seats, len(candidates)):
            if votes_for[candidates[i].id] == cutoff_votes:
                outcomes[i] = "tie"

    return ReportPosition(
        position_id=position.id,
        position_order=position.position_order,
        name_en=position.name_en,
        name_bn=position.name_bn,
        max_selections=seats,
        total_votes=sum(votes_for[c.id] for c in candidates),
        candidates=[
            ReportCandidate(
                candidate_id=c.id, voter_no=c.voter_no, name_en=c.name_en, name_bn=c.name_bn,
                display_order=c.display_order, panel=panels.get(c.id, ""), votes=votes_for[c.id],
                percentage=round(votes_for[c.id] / counted_ballots * 100, 2) if counted_ballots else 0.0,
                rank=ranks[i], outcome=outcomes[i],
            )
            for i, c in enumerate(candidates)
        ],
    )
