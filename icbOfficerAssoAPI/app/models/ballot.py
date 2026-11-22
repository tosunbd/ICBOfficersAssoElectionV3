"""Ballot model — one scanned ballot paper (one page of a scanned file)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time import utcnow


class BallotStatus:
    """Lifecycle of a ballot record."""

    PROCESSING = "processing"      # OCR in progress
    PROCESSED = "processed"        # read automatically, nothing suspicious
    NEEDS_REVIEW = "needs_review"  # counted, but an admin should double check
    REVIEWED = "reviewed"          # an admin confirmed / corrected the votes
    ERROR = "error"                # the file could not be read

    COUNTED = (PROCESSED, NEEDS_REVIEW, REVIEWED)
    ALL = (PROCESSING, PROCESSED, NEEDS_REVIEW, REVIEWED, ERROR)


class Ballot(Base):
    __tablename__ = "ballots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    election_id: Mapped[int] = mapped_column(Integer, ForeignKey("elections.id"), nullable=False)
    ballot_paper_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pdf_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(20), default="watcher")  # watcher | upload | manual
    original_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    completed_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=BallotStatus.PROCESSING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of strings
    boxes_detected: Mapped[int] = mapped_column(Integer, default=0)
    boxes_expected: Mapped[int] = mapped_column(Integer, default=0)
    total_votes_extracted: Mapped[int] = mapped_column(Integer, default=0)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    # Number printed in the box at the top right of the paper, see app/utils/paper_number.py
    printed_paper_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    election = relationship("Election", back_populates="ballots")
    votes = relationship("Vote", back_populates="ballot", cascade="all, delete-orphan", lazy="selectin")
