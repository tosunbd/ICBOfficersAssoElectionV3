"""Position model — each elected post in the election."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time import utcnow


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    election_id: Mapped[int] = mapped_column(Integer, ForeignKey("elections.id"), nullable=False)
    position_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_bn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    max_selections: Mapped[int] = mapped_column(Integer, default=1)  # e.g. 3 for executive members
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    election = relationship("Election", back_populates="positions")
    candidates = relationship(
        "Candidate", back_populates="position", cascade="all, delete-orphan",
        lazy="selectin", order_by="Candidate.display_order",
    )
    votes = relationship("Vote", back_populates="position", cascade="all, delete-orphan")
