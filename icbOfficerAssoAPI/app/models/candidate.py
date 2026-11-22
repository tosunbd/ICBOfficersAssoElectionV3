"""Candidate model — any number of candidates per position."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time import utcnow


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id"), nullable=False)
    election_id: Mapped[int] = mapped_column(Integer, ForeignKey("elections.id"), nullable=False)
    voter_no: Mapped[str] = mapped_column(String(50), nullable=False)
    name_en: Mapped[str] = mapped_column(String(300), nullable=False)
    name_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)  # order printed on the ballot
    vote_count: Mapped[int] = mapped_column(Integer, default=0)     # denormalised for fast reads
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    position = relationship("Position", back_populates="candidates")
    votes = relationship("Vote", back_populates="candidate", cascade="all, delete-orphan")
