"""SQLAlchemy async database setup for SQLite.

- WAL journal mode so the dashboard can read while ballots are being written.
- Foreign keys enforced.
- `init_db()` creates tables and adds any columns that were introduced after
  the database file was first created (a lightweight migration for SQLite).
- `switch_database()` moves the running app to another database file (one file
  per election year) without a restart.
"""

import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

def _configure_sqlite(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_engine(url: str) -> AsyncEngine:
    new_engine = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})
    event.listen(new_engine.sync_engine, "connect", _configure_sqlite)
    return new_engine


engine = make_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db(target: AsyncEngine | None = None) -> None:
    """Create missing tables and columns."""
    from app import models  # noqa: F401  (registers all models on Base.metadata)

    async with (target or engine).begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def switch_database(url: str) -> None:
    """Point every new session at another database file (created if missing).

    `AsyncSessionLocal` is re-bound in place, so modules that imported it keep
    working.  Sessions that are already open finish on the old file."""
    global engine
    new_engine = make_engine(url)
    await init_db(new_engine)
    old_engine, engine = engine, new_engine
    AsyncSessionLocal.configure(bind=new_engine)
    await old_engine.dispose()


def _add_missing_columns(connection) -> None:
    """Add columns that exist in the models but not yet in the SQLite file."""
    for table in Base.metadata.sorted_tables:
        existing = {
            row[1] for row in connection.execute(text(f'PRAGMA table_info("{table.name}")'))
        }
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(dialect=connection.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            default = column.default.arg if column.default is not None else None
            if default is not None and not callable(default):
                literal = f"'{default}'" if isinstance(default, str) else (int(default) if isinstance(default, bool) else default)
                ddl += f" DEFAULT {literal}"
            logger.info("Migrating: %s", ddl)
            connection.execute(text(ddl))
