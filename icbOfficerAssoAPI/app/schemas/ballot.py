"""Pydantic schemas for ballots and votes."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ballot_id: int
    candidate_id: int
    position_id: int
    is_valid: bool
    invalid_reason: str | None = None
    confidence_score: float
    created_at: datetime


class BallotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    election_id: int
    ballot_paper_no: str | None
    pdf_filename: str
    page_number: int = 1
    source: str = "watcher"
    status: str
    error_message: str | None
    ocr_warnings: list[str] = []
    boxes_detected: int = 0
    boxes_expected: int = 0
    total_votes_extracted: int
    is_valid: bool
    printed_paper_no: str | None = None   # number printed in the box at the top right (None = not readable)
    has_preview: bool = False
    scanned_at: datetime
    processed_at: datetime | None
    reviewed_at: datetime | None

    @field_validator("ocr_warnings", mode="before")
    @classmethod
    def _parse_warnings(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return [value]
        return value

    @classmethod
    def from_model(cls, ballot) -> "BallotResponse":
        data = cls.model_validate(ballot)
        data.has_preview = bool(ballot.preview_path)
        return data


class BallotDetailResponse(BallotResponse):
    votes: list[VoteResponse] = []

    @classmethod
    def from_model(cls, ballot) -> "BallotDetailResponse":
        data = cls.model_validate(ballot)
        data.has_preview = bool(ballot.preview_path)
        return data


class BallotListResponse(BaseModel):
    ballots: list[BallotResponse]
    total: int
    page: int
    per_page: int


class VoteCorrection(BaseModel):
    """One vote as confirmed by an admin."""

    candidate_id: int
    position_id: int
    is_valid: bool = True


class BallotReviewRequest(BaseModel):
    """Admin confirms or corrects the votes of a ballot."""

    ballot_paper_no: str | None = None
    votes: list[VoteCorrection] = Field(default_factory=list)


class ProcessFolderResponse(BaseModel):
    files_found: int
    files_processed: int
    files_errored: int
    details: list[dict]
    paused: bool = False          # counting was paused: the remaining files wait in Scanned


class BulkDeleteRequest(BaseModel):
    ballot_ids: list[int] = []
    election_id: int | None = None
    status_filter: str | None = None
    all_matching: bool = False


class BulkDeleteResponse(BaseModel):
    deleted: int
