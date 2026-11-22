"""FastAPI application entry point — ICB Officers' Association Election System."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.models.admin_user import AdminUser
from app.routers import admin, auth, ballots, candidates, dashboard, elections, reports
from app.services.file_watcher import file_watcher
from app.services.live_replay import live_replay
from app.utils.security import hash_password

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

APP_VERSION = "1.1.0"


async def create_default_admin() -> None:
    """Create the initial admin account on first start."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == settings.ADMIN_DEFAULT_USERNAME))
        if result.scalar_one_or_none():
            return
        db.add(AdminUser(
            username=settings.ADMIN_DEFAULT_USERNAME,
            password_hash=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
            full_name="System Administrator",
            role="superadmin",
        ))
        await db.commit()
        logger.info("Default admin user '%s' created", settings.ADMIN_DEFAULT_USERNAME)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting ICB Election API v%s", APP_VERSION)
    await init_db()
    await create_default_admin()
    for folder in (settings.scanned_path, settings.completed_path, settings.failed_path, settings.preview_path):
        logger.info("Folder ready: %s", folder)

    if settings.AUTO_PROCESS_ENABLED:
        file_watcher.start()
    else:
        logger.info("AUTO_PROCESS_ENABLED=false: files must be processed with 'Scan folder' or upload")

    logger.info("API is ready")
    yield
    live_replay.stop_all()
    await file_watcher.stop()
    logger.info("API stopped")


app = FastAPI(
    title="ICB Officers' Association Election System",
    description="Ballot scanning, vote counting and live dashboard for the ICB Officers' Association election.",
    version=APP_VERSION,
    lifespan=lifespan,
)

origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,  # browsers reject credentials with a wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(elections.router)
app.include_router(candidates.router)
app.include_router(ballots.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(reports.router)


@app.get("/", tags=["Health"])
async def root():
    return {"name": "ICB Officers' Association Election System", "version": APP_VERSION, "status": "running"}


@app.get("/api/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "auto_process_enabled": settings.AUTO_PROCESS_ENABLED,
        "file_watcher": file_watcher.is_running,
        "scanned_folder": str(settings.scanned_path),
        "completed_folder": str(settings.completed_path),
    }
