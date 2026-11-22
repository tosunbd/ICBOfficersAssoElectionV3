"""Vote counter — aggregates and ranks results for the dashboard."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ballot, Candidate, Election, Position, Vote
from app.models.ballot import BallotStatus
from app.schemas.dashboard import CandidateResult, DashboardResponse, DashboardStats, PositionResult

logger = logging.getLogger(__name__)


class VoteCounter:
    async def get_dashboard_data(
        self, db: AsyncSession, election_id: int, include_results: bool | None = None,
        up_to_ballot_id: int | None = None,
    ) -> DashboardResponse:
        """Build the dashboard payload.

        `include_results=None` means "only if the dashboard is published";
        admins pass True to always see the numbers.  `up_to_ballot_id` gives
        the totals as they stood once that ballot was counted (the replay that
        follows Publish); 0 means before the first ballot.
        """
        # populate_existing: a long folder scan keeps one session for minutes; without it the
        # election would still look as it did when the scan began (e.g. "not published" after
        # Publish was pressed), and the live screen would hide the results after every ballot
        result = await db.execute(
            select(Election).where(Election.id == election_id).execution_options(populate_existing=True)
        )
        election = result.scalar_one_or_none()
        if not election:
            raise ValueError(f"Election {election_id} not found")

        stats = await self.get_stats(db, election, up_to_ballot_id)
        visible = election.dashboard_published if include_results is None else include_results
        positions = []
        if visible:
            counts = None if up_to_ballot_id is None else await self._counts_up_to(db, election_id, up_to_ballot_id)
            positions = await self._position_results(db, election_id, stats.counted_ballots, counts)

        return DashboardResponse(
            election_id=election.id,
            election_title=election.title,
            election_title_bn=election.title_bn,
            election_year=election.year,
            election_status=election.status,
            dashboard_published=election.dashboard_published,
            dashboard_paused=election.dashboard_paused,
            counting_paused=bool(election.counting_paused),
            results_visible=visible,
            stats=stats,
            positions=positions,
        )

    async def get_stats(self, db: AsyncSession, election: Election, up_to_ballot_id: int | None = None) -> DashboardStats:
        query = select(Ballot.status, func.count(Ballot.id)).where(Ballot.election_id == election.id)
        if up_to_ballot_id is not None:
            query = query.where(Ballot.id <= up_to_ballot_id)
        result = await db.execute(query.group_by(Ballot.status))
        by_status = dict(result.all())
        total = sum(by_status.values())
        counted = sum(by_status.get(s, 0) for s in BallotStatus.COUNTED)
        turnout = (counted / election.total_voters * 100) if election.total_voters else 0.0
        return DashboardStats(
            total_ballots=total,
            counted_ballots=counted,
            processed_ballots=by_status.get(BallotStatus.PROCESSED, 0),
            needs_review_ballots=by_status.get(BallotStatus.NEEDS_REVIEW, 0),
            reviewed_ballots=by_status.get(BallotStatus.REVIEWED, 0),
            error_ballots=by_status.get(BallotStatus.ERROR, 0),
            pending_ballots=by_status.get(BallotStatus.PROCESSING, 0),
            total_voters=election.total_voters,
            turnout_percentage=round(turnout, 2),
        )

    @staticmethod
    async def _counts_up_to(db: AsyncSession, election_id: int, up_to_ballot_id: int) -> dict[int, int]:
        """Valid votes per candidate from the ballots up to and including
        `up_to_ballot_id` (same rule as the recount)."""
        result = await db.execute(
            select(Vote.candidate_id, func.count(Vote.id))
            .join(Ballot, Vote.ballot_id == Ballot.id)
            .where(
                Ballot.election_id == election_id, Ballot.id <= up_to_ballot_id,
                Ballot.status.in_(BallotStatus.COUNTED), Ballot.is_valid.is_(True), Vote.is_valid.is_(True),
            )
            .group_by(Vote.candidate_id)
        )
        return dict(result.all())

    async def _position_results(
        self, db: AsyncSession, election_id: int, counted: int, counts: dict[int, int] | None = None
    ) -> list[PositionResult]:
        """`counts` overrides the stored counters (candidate id -> votes)."""
        result = await db.execute(
            select(Position).where(Position.election_id == election_id).order_by(Position.position_order)
        )
        positions = result.scalars().all()

        output: list[PositionResult] = []
        def votes_of(candidate: Candidate) -> int:
            return candidate.vote_count if counts is None else counts.get(candidate.id, 0)

        for position in positions:
            candidates = sorted(
                position.candidates, key=lambda c: (-votes_of(c), c.display_order, c.id)
            )
            total_votes = sum(votes_of(c) for c in candidates)
            ranked: list[CandidateResult] = []
            previous_votes, rank = None, 0
            for index, candidate in enumerate(candidates, start=1):
                votes = votes_of(candidate)
                if votes != previous_votes:
                    rank = index  # tied candidates share a rank
                    previous_votes = votes
                ranked.append(CandidateResult(
                    candidate_id=candidate.id,
                    voter_no=candidate.voter_no,
                    name_en=candidate.name_en,
                    name_bn=candidate.name_bn,
                    vote_count=votes,
                    percentage=round(votes / counted * 100, 2) if counted else 0.0,
                    rank=rank,
                    is_leading=rank <= position.max_selections and votes > 0,
                ))
            output.append(PositionResult(
                position_id=position.id,
                position_order=position.position_order,
                name_en=position.name_en,
                name_bn=position.name_bn,
                max_selections=position.max_selections,
                total_votes_cast=total_votes,
                candidates=ranked,
            ))
        return output


vote_counter = VoteCounter()
