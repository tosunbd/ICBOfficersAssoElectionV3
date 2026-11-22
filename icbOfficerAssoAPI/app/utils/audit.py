"""Audit-log helper."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record(db: AsyncSession, user_id: int | None, action: str, details: str | None = None) -> None:
    """Queue an audit entry on the session (caller commits)."""
    db.add(AuditLog(admin_user_id=user_id, action=action, details=details))
