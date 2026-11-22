"""Admin router — dashboard controls, recount, audit log, system status."""

import os
import re
import string
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PROJECT_ROOT, settings
from app import database
from app.database import get_db
from app.models import AdminUser, AuditLog, Election
from app.models.election import ElectionStatus
from app.schemas.admin import (
    AuditLogEntry, DatabaseFile, DatabaseInfo, DatabaseYearRequest, FolderEntry, FolderListing,
    FolderUpdateRequest, SystemStatus,
)
from app.services.ballot_processor import ballot_processor
from app.services.events import notifier
from app.services.file_watcher import file_watcher
from app.services.live_replay import live_replay
from app.utils import audit
from app.utils.security import get_current_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])


async def _get_election(db: AsyncSession, election_id: int) -> Election:
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")
    return election


@router.put("/dashboard/{election_id}/publish")
async def toggle_dashboard_publish(
    election_id: int,
    publish: bool,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Show or hide results on the public dashboard.

    Publishing replays the count on the public screen: every ballot from the
    first, the election's `ballot_display_seconds` each, with the totals
    growing from zero."""
    election = await _get_election(db, election_id)
    election.dashboard_published = publish
    audit.record(db, current_user.id, "dashboard_publish" if publish else "dashboard_unpublish",
                 f"Election #{election_id}: dashboard {'published' if publish else 'unpublished'}")
    await db.commit()
    if publish:
        live_replay.start(election_id, election.ballot_display_seconds)
    else:
        live_replay.stop(election_id)
    notifier.notify()
    return {"status": "published" if publish else "unpublished", "election_id": election_id,
            "replay": live_replay.status(election_id)}


@router.get("/dashboard/{election_id}/replay")
async def replay_status(election_id: int, current_user: AdminUser = Depends(get_current_user)):
    """Progress of the ballot-by-ballot replay shown after Publish."""
    return live_replay.status(election_id)


@router.post("/dashboard/{election_id}/replay")
async def restart_replay(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Show the count again from the first ballot."""
    election = await _get_election(db, election_id)
    if not election.dashboard_published:
        raise HTTPException(status_code=400, detail="Publish the results first")
    if not live_replay.start(election_id, election.ballot_display_seconds):
        raise HTTPException(status_code=400, detail="The replay is switched off (PUBLISH_REPLAY_ENABLED=false)")
    audit.record(db, current_user.id, "dashboard_replay", f"Election #{election_id}: count replayed from the first ballot")
    await db.commit()
    return live_replay.status(election_id)


@router.delete("/dashboard/{election_id}/replay")
async def skip_replay(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Stop the replay; the public screen shows the final totals at once."""
    await _get_election(db, election_id)
    if live_replay.is_running(election_id):
        live_replay.stop(election_id)
        audit.record(db, current_user.id, "dashboard_replay_skip", f"Election #{election_id}: replay skipped to the totals")
        await db.commit()
    return live_replay.status(election_id)


@router.put("/dashboard/{election_id}/pause")
async def toggle_dashboard_pause(
    election_id: int,
    pause: bool,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Freeze or resume live updates on the public dashboard."""
    election = await _get_election(db, election_id)
    election.dashboard_paused = pause
    audit.record(db, current_user.id, "dashboard_pause" if pause else "dashboard_resume",
                 f"Election #{election_id}: dashboard {'paused' if pause else 'resumed'}")
    await db.commit()
    notifier.notify()
    return {"status": "paused" if pause else "resumed", "election_id": election_id}


@router.put("/counting/{election_id}/pause")
async def toggle_counting_pause(
    election_id: int,
    pause: bool,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """PAUSE / START the count (button on the live screen).  While paused no
    ballot is read: scanned files wait in the Scanned folder, the replay after
    Publish holds, and the live screen says so.  START carries on in order:
    the files waiting in the Scanned folder are read again at once, as if Scan
    had been pressed (the folder watcher, when it runs, picks them up itself)."""
    election = await _get_election(db, election_id)
    if election.counting_paused != pause:
        election.counting_paused = pause
        audit.record(db, current_user.id, "counting_pause" if pause else "counting_start",
                     f"Election #{election_id}: counting {'paused' if pause else 'started again'}")
        await db.commit()
        notifier.notify()
    scan_resumed = False
    if not pause and not file_watcher.is_running:
        scan_resumed = ballot_processor.resume_folder_scan(election_id)
    return {"status": "paused" if pause else "running", "election_id": election_id, "scan_resumed": scan_resumed}


@router.put("/election/{election_id}/status")
async def update_election_status(
    election_id: int,
    new_status: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """draft -> active -> completed.  Only ONE election can be active: the
    folder watcher feeds scanned files into the active election."""
    if new_status not in ElectionStatus.ALL:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {list(ElectionStatus.ALL)}")
    election = await _get_election(db, election_id)
    old_status = election.status

    if new_status == ElectionStatus.ACTIVE:
        others = (await db.execute(
            select(Election).where(Election.status == ElectionStatus.ACTIVE, Election.id != election_id)
        )).scalars().all()
        for other in others:
            other.status = ElectionStatus.COMPLETED
            audit.record(db, current_user.id, "election_status_change",
                         f"Election #{other.id}: active -> completed (another election was activated)")

    election.status = new_status
    audit.record(db, current_user.id, "election_status_change", f"Election #{election_id}: {old_status} -> {new_status}")
    await db.commit()
    notifier.notify()
    return {"status": new_status, "election_id": election_id}


@router.post("/election/{election_id}/recount")
async def recount_votes(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Rebuild the vote counters from the stored vote records."""
    await _get_election(db, election_id)
    await ballot_processor.recount_votes(db, election_id)
    audit.record(db, current_user.id, "vote_recount", f"Election #{election_id}: full recount executed")
    await db.commit()
    return {"status": "recount_complete", "election_id": election_id}


@router.get("/audit-log", response_model=list[AuditLogEntry])
async def get_audit_log(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(AuditLog, AdminUser.username)
        .outerjoin(AdminUser, AuditLog.admin_user_id == AdminUser.id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return [
        AuditLogEntry(
            id=log.id, admin_user_id=log.admin_user_id, username=username,
            action=log.action, details=log.details, created_at=log.created_at,
        )
        for log, username in result.all()
    ]


@router.get("/system", response_model=SystemStatus)
async def system_status(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Health of the automatic processing pipeline."""
    active = (await db.execute(
        select(Election.id).where(Election.status == ElectionStatus.ACTIVE).order_by(Election.id.desc()).limit(1)
    )).scalar_one_or_none()
    waiting = sum(
        1 for p in settings.scanned_path.iterdir() if p.is_file() and ballot_processor.is_supported(p)
    )
    return SystemStatus(
        auto_process_enabled=settings.AUTO_PROCESS_ENABLED,
        watcher_running=file_watcher.is_running,
        os_events_active=file_watcher.os_events_active,
        queue_size=file_watcher.queue_size,
        files_waiting=waiting,
        files_processed_since_start=file_watcher.files_processed,
        last_error=file_watcher.last_error,
        active_election_id=active,
        scanned_folder=str(settings.scanned_path),
        completed_folder=str(settings.completed_path),
        failed_folder=str(settings.failed_path),
        ocr_dpi=settings.OCR_DPI,
        mark_threshold=settings.MARK_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Folder picker: browse the server's folders and choose Scanned / Completed
# ---------------------------------------------------------------------------

def _roots() -> list[FolderEntry]:
    if os.name == "nt":
        drives = [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
        return [FolderEntry(name=d.rstrip("\\"), path=d) for d in drives]
    return [FolderEntry(name="/", path="/")]


def _shortcuts() -> list[FolderEntry]:
    items = [
        ("Scanned (current)", settings.scanned_path),
        ("Completed (current)", settings.completed_path),
        ("Project data", PROJECT_ROOT / "data"),
        ("Home", Path.home()),
    ]
    return [FolderEntry(name=name, path=str(path)) for name, path in items if path.is_dir()]


@router.get("/fs/browse", response_model=FolderListing)
async def browse_folders(
    path: str | None = Query(None, description="Folder to list; empty lists the drives"),
    current_user: AdminUser = Depends(get_current_user),
):
    """List the sub-folders of `path` (folders only, never file contents)."""
    if not path:
        return FolderListing(path="", parent=None, folders=_roots(), shortcuts=_shortcuts())
    folder = Path(path).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a folder: {path}")
    folder = folder.resolve()
    try:
        children = sorted(
            (child for child in folder.iterdir() if child.is_dir() and not child.name.startswith((".", "$"))),
            key=lambda child: child.name.lower(),
        )
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot open {folder}: {exc.strerror or exc}")
    parent = "" if folder.parent == folder else str(folder.parent)
    return FolderListing(
        path=str(folder), parent=parent,
        folders=[FolderEntry(name=child.name, path=str(child)) for child in children[:500]],
        shortcuts=_shortcuts(),
    )


@router.put("/folders", response_model=SystemStatus)
async def update_folders(
    body: FolderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Choose the Scanned / Completed / Failed folders.  Saved to disk, applied immediately."""
    changes: dict[str, str] = {}
    for key in settings.FOLDER_KEYS:
        value = getattr(body, key)
        if not value or not value.strip():
            continue
        folder = Path(value.strip()).expanduser()
        if not folder.is_absolute():
            raise HTTPException(status_code=400, detail=f"Use a full path for {key.replace('_', ' ')}")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Cannot create {folder}: {exc.strerror or exc}")
        changes[key] = str(folder.resolve())
    if not changes:
        raise HTTPException(status_code=400, detail="No folder given")

    final = {key: changes.get(key) or str(settings._resolve(getattr(settings, attr)))
             for key, attr in settings.FOLDER_KEYS.items()}
    if final["scanned_folder"] in (final["completed_folder"], final["failed_folder"]):
        raise HTTPException(status_code=400, detail="The Scanned folder must differ from the Completed and Failed folders")

    settings.save_folder_overrides(changes)
    if file_watcher.is_running:  # the OS watcher is bound to the old folder
        await file_watcher.stop()
        file_watcher.start()
    audit.record(db, current_user.id, "folders_update",
                 "; ".join(f"{key.replace('_', ' ')} -> {value}" for key, value in changes.items()))
    await db.commit()
    return await system_status(db, current_user)


# ---------------------------------------------------------------------------
# Database file per election year (icbOfficerAssoDB{Year}.db)
# ---------------------------------------------------------------------------

def _year_files() -> list[DatabaseFile]:
    """The other icbOfficerAssoDB<year>.db files in the database folder."""
    template = settings.sqlite_file(settings._resolve_sqlite_url(settings.DATABASE_URL))
    if template is None or not settings.database_url_has_year:
        return []
    head, _, tail = re.split(r"(\{year\})", template.name, maxsplit=1, flags=re.IGNORECASE)
    pattern = re.compile(rf"^{re.escape(head)}(\d{{4}}){re.escape(tail)}$", re.IGNORECASE)
    files = []
    for path in template.parent.glob("*"):
        match = pattern.match(path.name)
        if match and path.is_file():
            stat = path.stat()
            year = int(match.group(1))
            files.append(DatabaseFile(
                year=year, file_name=path.name, size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime), current=year == settings.database_year,
            ))
    return sorted(files, key=lambda f: f.year, reverse=True)


def _database_info() -> DatabaseInfo:
    path = settings.database_file
    exists = path is not None and path.exists()
    return DatabaseInfo(
        year=settings.database_year,
        per_year=settings.database_url_has_year,
        file_name=path.name if path else None,
        path=str(path) if path else None,
        size_bytes=path.stat().st_size if exists else None,
        files=_year_files(),
    )


@router.get("/database", response_model=DatabaseInfo)
async def database_info(current_user: AdminUser = Depends(get_current_user)):
    return _database_info()


@router.put("/database", response_model=DatabaseInfo)
async def switch_database_year(
    body: DatabaseYearRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Use the database file of another election year (created empty if it does not exist).

    Admin accounts are copied into a new file so the same logins keep working."""
    if not settings.database_url_has_year:
        raise HTTPException(status_code=400, detail="DATABASE_URL in .env has no {Year} placeholder, so the year cannot be changed here")
    old_year = settings.database_year
    if body.year == old_year:
        return _database_info()

    admins = (await db.execute(select(AdminUser))).scalars().all()
    accounts = [(a.username, a.password_hash, a.full_name, a.role) for a in admins]
    audit.record(db, current_user.id, "database_switch", f"Database year {old_year} -> {body.year}")
    await db.commit()

    live_replay.stop_all()  # its ballots belong to the old file
    watching = file_watcher.is_running
    if watching:  # no ballot may be written while the file changes
        await file_watcher.stop()
    try:
        await database.switch_database(settings.database_url_for(body.year))
        settings.save_database_year(body.year)
    finally:
        if watching:
            file_watcher.start()

    async with database.AsyncSessionLocal() as new_db:
        known = set((await new_db.execute(select(AdminUser.username))).scalars().all())
        for username, password_hash, full_name, role in accounts:
            if username not in known:
                new_db.add(AdminUser(username=username, password_hash=password_hash, full_name=full_name, role=role))
        await new_db.flush()
        user_id = (await new_db.execute(
            select(AdminUser.id).where(AdminUser.username == current_user.username)
        )).scalar_one_or_none()
        audit.record(new_db, user_id, "database_switch", f"Database year {old_year} -> {body.year}")
        await new_db.commit()
    notifier.notify()
    return _database_info()
