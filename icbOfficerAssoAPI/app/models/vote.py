"""Vote model — individual vote record from a ballot."""

from datetime import datetime
from app.utils.time import utcnow
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ballot_id: Mapped[int] = mapped_column(Integer, ForeignKey("ballots.id"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(Integer, ForeignKey("candidates.id"), nullable=False)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id"), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    invalid_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)  # why it is not counted
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    ballot = relationship("Ballot", back_populates="votes")
    candidate = relationship("Candidate", back_populates="votes")
    position = relationship("Position", back_populates="votes")
