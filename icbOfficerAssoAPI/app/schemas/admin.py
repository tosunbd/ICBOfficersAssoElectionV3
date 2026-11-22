"""Pydantic schemas for admin endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    id: int
    admin_user_id: int | None
    username: str | None
    action: str
    details: str | None
    created_at: datetime | None


class SystemStatus(BaseModel):
    auto_process_enabled: bool
    watcher_running: bool
    os_events_active: bool
    queue_size: int
    files_waiting: int
    files_processed_since_start: int
    last_error: str | None
    active_election_id: int | None
    scanned_folder: str
    completed_folder: str
    failed_folder: str
    ocr_dpi: int
    mark_threshold: float


class FolderEntry(BaseModel):
    name: str
    path: str


class FolderListing(BaseModel):
    """One level of the server's folder tree, for the admin folder picker."""
    path: str                   # "" = the list of drives / roots
    parent: str | None          # None at the top; "" = back to the drive list
    folders: list[FolderEntry]
    shortcuts: list[FolderEntry]


class FolderUpdateRequest(BaseModel):
    scanned_folder: str | None = None
    completed_folder: str | None = None
    failed_folder: str | None = None


class DatabaseFile(BaseModel):
    year: int
    file_name: str
    size_bytes: int
    modified_at: datetime
    current: bool


class DatabaseInfo(BaseModel):
    """The database file in use and the other per-year files next to it."""
    year: int
    per_year: bool              # DATABASE_URL contains {Year}
    file_name: str | None
    path: str | None
    size_bytes: int | None
    files: list[DatabaseFile]


class DatabaseYearRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
