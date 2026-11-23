"""Pydantic schemas for elections and positions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

DISPLAY_SECONDS = {"ge": 1, "le": 600}  # seconds the public screen holds the totals of each ballot


# --- Positions ------------------------------------------------------------
class PositionBase(BaseModel):
    position_order: int
    name_en: str
    name_bn: str | None = None
    max_selections: int = Field(default=1, ge=1)


class PositionCreate(PositionBase):
    pass


class PositionUpdate(BaseModel):
    position_order: int | None = None
    name_en: str | None = None
    name_bn: str | None = None
    max_selections: int | None = Field(default=None, ge=1)


class PositionResponse(PositionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    election_id: int
    created_at: datetime


# --- Elections ------------------------------------------------------------
class ElectionBase(BaseModel):
    title: str
    title_bn: str | None = None
    year: int
    description: str | None = None
    total_voters: int = Field(default=455, ge=1)
    ballot_display_seconds: int = Field(default_factory=lambda: settings.LIVE_BALLOT_DISPLAY_SECONDS, **DISPLAY_SECONDS)


class ElectionCreate(ElectionBase):
    pass


class ElectionUpdate(BaseModel):
    title: str | None = None
    title_bn: str | None = None
    year: int | None = None
    description: str | None = None
    status: str | None = None
    dashboard_published: bool | None = None
    dashboard_paused: bool | None = None
    total_voters: int | None = Field(default=None, ge=1)
    ballot_display_seconds: int | None = Field(default=None, **DISPLAY_SECONDS)


class ElectionResponse(ElectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    dashboard_published: bool
    dashboard_paused: bool
    counting_paused: bool = False
    created_at: datetime
    updated_at: datetime


class ElectionDetailResponse(ElectionResponse):
    positions: list[PositionResponse] = []
