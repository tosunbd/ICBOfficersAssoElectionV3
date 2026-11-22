"""Admin user model."""

from datetime import datetime
from app.utils.time import utcnow
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="admin")  # superadmin, admin, operator
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    audit_logs = relationship("AuditLog", back_populates="admin_user")
