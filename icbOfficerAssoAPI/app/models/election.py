"""Election model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time import utcnow


class ElectionStatus:
    DRAFT = "draft"          # being set up (positions / candidates)
    ACTIVE = "active"        # ballots are being scanned and counted
    COMPLETED = "completed"  # counting finished
    ALL = (DRAFT, ACTIVE, COMPLETED)


class Election(Base):
    __tablename__ = "elections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_bn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ElectionStatus.DRAFT)
    dashboard_published: Mapped[bool] = mapped_column(Boolean, default=False)
    dashboard_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # PAUSE on the live screen: no ballot is read (files wait in Scanned) until START
    counting_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    total_voters: Mapped[int] = mapped_column(Integer, default=1000)
    # how long the public screen shows each ballot (live count and the replay after Publish)
    ballot_display_seconds: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    positions = relationship(
        "Position", back_populates="election", cascade="all, delete-orphan",
        lazy="selectin", order_by="Position.position_order",
    )
    ballots = relationship("Ballot", back_populates="election", cascade="all, delete-orphan")
