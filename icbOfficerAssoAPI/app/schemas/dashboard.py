"""Pydantic schemas for the dashboard and the public live screen."""

from pydantic import BaseModel


class CandidateResult(BaseModel):
    candidate_id: int
    voter_no: str
    name_en: str
    name_bn: str | None
    vote_count: int
    percentage: float
    rank: int
    is_leading: bool


class PositionResult(BaseModel):
    position_id: int
    position_order: int
    name_en: str
    name_bn: str | None
    max_selections: int
    total_votes_cast: int
    candidates: list[CandidateResult]


class DashboardStats(BaseModel):
    total_ballots: int
    counted_ballots: int          # processed + needs_review + reviewed
    processed_ballots: int
    needs_review_ballots: int
    reviewed_ballots: int
    error_ballots: int
    pending_ballots: int
    total_voters: int
    turnout_percentage: float


class ReplayProgress(BaseModel):
    """Where the replay that follows Publish has got to (ballot 12 of 230)."""

    position: int
    total: int


class DashboardResponse(BaseModel):
    election_id: int
    election_title: str
    election_title_bn: str | None
    election_year: int
    election_status: str
    dashboard_published: bool
    dashboard_paused: bool
    counting_paused: bool = False
    results_visible: bool         # False -> positions is empty (not published)
    stats: DashboardStats
    positions: list[PositionResult]
    replay: ReplayProgress | None = None  # the count is being replayed after Publish


class ActiveElectionResponse(BaseModel):
    id: int
    title: str
    title_bn: str | None
    year: int
    status: str
    dashboard_published: bool
    dashboard_paused: bool
    counting_paused: bool = False
    live_display_seconds: int = 2


class LiveVote(BaseModel):
    position_id: int
    position_order: int
    position_name_en: str
    position_name_bn: str | None
    candidate_id: int
    voter_no: str
    candidate_name_en: str
    candidate_name_bn: str | None
    is_valid: bool
    invalid_reason: str | None = None
    confidence: float


class LiveBallotEvent(BaseModel):
    """Pushed to the public screen for every scanned file, in order.

    `kind`: "counted" (read by the machine), "reread" (read again on the
    committee's request), "reviewed" (votes corrected by the committee) or
    "unreadable" (the file could not be read; set aside, nothing counted).
    """

    ballot_id: int
    election_id: int
    sequence_no: int              # running number of counted ballots (1, 2, 3 ...)
    ballot_paper_no: str | None
    pdf_filename: str
    page_number: int
    status: str
    kind: str = "counted"
    error_message: str | None = None
    is_valid: bool = True         # False when the committee voided the whole ballot
    has_preview: bool
    votes: list[LiveVote]
    display_seconds: int
    results: DashboardResponse    # totals AFTER this ballot was counted
    replay: ReplayProgress | None = None  # set while the count is replayed after Publish
