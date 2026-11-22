"""Time helpers."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (what SQLite stores)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
