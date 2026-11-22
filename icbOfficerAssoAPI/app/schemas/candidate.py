"""Pydantic schemas for candidates."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CandidateBase(BaseModel):
    voter_no: str
    name_en: str
    name_bn: str | None = None
    display_order: int = 0


class CandidateCreate(CandidateBase):
    position_id: int
    election_id: int


class CandidateUpdate(BaseModel):
    voter_no: str | None = None
    name_en: str | None = None
    name_bn: str | None = None
    display_order: int | None = None


class CandidateResponse(CandidateBase):
    id: int
    position_id: int
    election_id: int
    vote_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateBulkCreate(BaseModel):
    """Create multiple candidates at once."""
    candidates: list[CandidateCreate]
