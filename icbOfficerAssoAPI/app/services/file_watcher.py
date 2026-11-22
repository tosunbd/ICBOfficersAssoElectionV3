"""Folder watcher — automatic processing of files dropped in `Scanned/`.

Two sources feed one asyncio queue:

* `watchdog` OS notifications (instant reaction on a local disk), and
* a periodic sweep of the folder (catches files the OS did not report, e.g.
  network shares or Docker bind mounts on Windows, and anything that was
  already there when the server started).

A single worker task drains the queue.  Files are only read once they have
stopped growing, and are processed into the election whose status is
`active`.  If no election is active the files simply wait in the folder.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Election
from app.models.election import ElectionStatus
from app.services.ballot_processor import ballot_processor

logger = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    """Pushes new file paths from the watchdog thread onto the asyncio queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop, enqueue) -> None:
        self._loop = loop
        self._enqueue = enqueue

    def _push(self, raw_path: str | bytes) -> None:
        path = Path(raw_path.decode() if isinstance(raw_path, bytes) else raw_path)
        if ballot_processor.is_supported(path):
            self._loop.call_soon_threadsafe(self._enqueue, path)

    def on_created(self, event):
        if not event.is_directory:
            self._push(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._push(event.dest_path)


class FileWatcher:
    def __init__(self) -> None:
        self._observer: Observer | None = None
        self._queue: asyncio.Queue[Path] | None = None
        self._queued: set[str] = set()
        self._attempts: dict[str, int] = {}
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._warned_no_election = False
        self._warned_no_candidates = False
        self.last_error: str | None = None
        self.files_processed = 0

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._running:
            return
        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        folder = settings.scanned_path
        logger.info("Watching folder: %s", folder)

        try:
            self._observer = Observer()
            self._observer.schedule(_Handler(loop, self._enqueue), str(folder), recursive=False)
            self._observer.daemon = True
            self._observer.start()
        except Exception as exc:  # polling sweep still works without OS events
            logger.warning("OS file notifications unavailable (%s); relying on polling", exc)
            self._observer = None

        self._tasks = [
            loop.create_task(self._worker(), name="scanned-folder-worker"),
            loop.create_task(self._sweeper(), name="scanned-folder-sweeper"),
        ]
        self._running = True

    async def stop(self) -> None:
        if not self._running:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._running = False
        logger.info("Folder watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def os_events_active(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    @property
    def queue_size(self) -> int:
        return len(self._queued)

    # ---------------------------------------------------------------- queue
    def _enqueue(self, path: Path) -> None:
        key = str(path.resolve())
        if key in self._queued or key in ballot_processor.in_flight:
            return
        self._queued.add(key)
        assert self._queue is not None
        self._queue.put_nowait(path)

    async def _sweeper(self) -> None:
        """Periodically enqueue every supported file in the folder."""
        while True:
            try:
                for path in sorted(settings.scanned_path.iterdir()):
                    if path.is_file() and ballot_processor.is_supported(path):
                        self._enqueue(path)
            except Exception as exc:
                logger.warning("Folder sweep failed: %s", exc)
            await asyncio.sleep(settings.SCAN_POLL_INTERVAL)

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            path = await self._queue.get()
            key = str(path.resolve())
            try:
                await self._handle(path, key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{path.name}: {exc}"
                logger.exception("Unexpected error while processing %s", path.name)
                await self._give_up_if_needed(path, key)
            finally:
                self._queued.discard(key)
                self._queue.task_done()

    # -------------------------------------------------------------- handling
    async def _handle(self, path: Path, key: str) -> None:
        if not path.exists() or key in ballot_processor.in_flight:
            return
        if not await self._wait_until_stable(path):
            return

        election_id = await self._active_election_id()
        if election_id is None:
            if not self._warned_no_election:
                logger.warning(
                    "Files are waiting in %s but no election is ACTIVE. "
                    "Set an election to 'active' in the admin panel.", settings.scanned_path,
                )
                self._warned_no_election = True
            return
        self._warned_no_election = False

        async with AsyncSessionLocal() as db:
            if await ballot_processor.counting_paused(db, election_id):
                return  # PAUSE on the live screen: the file waits; the sweep queues it again after START
            if not await ballot_processor.candidate_count(db, election_id):
                # files wait in the Scanned folder until the candidate list is entered
                if not self._warned_no_candidates:
                    logger.warning("Files are waiting in %s but the active election has no candidates yet.", settings.scanned_path)
                    self._warned_no_candidates = True
                return
            self._warned_no_candidates = False
            ballots = await ballot_processor.process_file(db, path, election_id, source="watcher")
        if ballots:
            self.files_processed += 1
            self._attempts.pop(key, None)
            if settings.PROCESS_DELAY_SECONDS > 0:
                await asyncio.sleep(settings.PROCESS_DELAY_SECONDS)

    async def _wait_until_stable(self, path: Path) -> bool:
        """Return once the file size has stopped changing (scanner finished writing)."""
        last_size = -1
        for _ in range(40):  # at most ~60 s with the default interval
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                return False
            if size > 0 and size == last_size:
                return True
            last_size = size
            await asyncio.sleep(settings.FILE_STABLE_SECONDS)
        logger.warning("%s kept changing size; processing anyway", path.name)
        return True

    async def _give_up_if_needed(self, path: Path, key: str) -> None:
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if self._attempts[key] >= settings.MAX_PROCESS_ATTEMPTS and path.exists():
            dest = ballot_processor._move(path, settings.failed_path)
            logger.error("Giving up on %s after %d attempts -> %s", path.name, self._attempts[key], dest)
            self._attempts.pop(key, None)

    @staticmethod
    async def _active_election_id() -> int | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Election.id)
                .where(Election.status == ElectionStatus.ACTIVE)
                .order_by(Election.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()


file_watcher = FileWatcher()
