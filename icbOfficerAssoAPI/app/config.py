"""Application configuration.

All settings can be overridden with environment variables or a `.env` file.
The `.env` file is looked up in the project root (next to docker-compose.yml)
and then inside `icbOfficerAssoAPI/`.

Relative folder paths are resolved against the PROJECT ROOT, never against the
current working directory, so it does not matter from where uvicorn is started.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[1]  # .../icbOfficerAssoAPI
PROJECT_ROOT = API_DIR.parent                   # .../ICBOfficersAssoElection


class Settings(BaseSettings):
    """Runtime settings (see .env.example for documentation of each value)."""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---------------------------------------------------------
    # {Year} is replaced by the election year, so every election gets its own
    # database file (kept afterwards as the record of that election).
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/icbOfficerAssoDB{Year}.db"
    ELECTION_YEAR: int = 0  # 0 = the current calendar year
    # The year chosen in the admin panel (Settings -> Database) is saved here
    # and takes precedence over ELECTION_YEAR.
    DATABASE_SETTINGS_FILE: str = "./data/database_settings.json"

    @field_validator("ELECTION_YEAR", mode="before")
    @classmethod
    def _blank_year(cls, value):
        return 0 if value in ("", None) else value

    # --- Folders ----------------------------------------------------------
    SCANNED_FOLDER_PATH: str = "./data/Scanned"      # drop scanned PDFs here
    COMPLETED_FOLDER_PATH: str = "./data/Completed"  # processed files are moved here
    FAILED_FOLDER_PATH: str = "./data/Failed"        # unreadable files are moved here
    PREVIEW_FOLDER_PATH: str = "./data/Previews"     # PNG previews used by the review UI
    # Folders chosen in the admin panel (Settings -> Folders) are saved here and
    # take precedence over the values above.
    FOLDER_SETTINGS_FILE: str = "./data/folder_settings.json"

    # --- Automatic processing --------------------------------------------
    AUTO_PROCESS_ENABLED: bool = True   # watch the Scanned folder and process new files
    SCAN_POLL_INTERVAL: float = 5.0     # seconds between folder sweeps (backup for OS events)
    FILE_STABLE_SECONDS: float = 1.5    # wait until a file stops growing before reading it
    MAX_PROCESS_ATTEMPTS: int = 3       # give up on a file after this many failures
    PROCESS_DELAY_SECONDS: float = 0.0  # pause between files (e.g. 2 to watch ballots appear one by one)

    # --- Mark detection ---------------------------------------------------
    OCR_DPI: int = 200                  # render resolution for PDF pages
    BALLOT_COLUMNS: int = 2             # candidates printed side by side per row
    MARK_THRESHOLD: float = 0.06        # ink ratio inside a box that counts as "marked"
    # A box with less ink than MARK_THRESHOLD has still been touched when one single patch
    # of ink (a dot, a light stroke) covers at least this share of it; scanner specks are
    # far smaller.  A touched box is a mark: counted when it is the only one for its
    # post, and it voids the post when another box of the post is marked too.
    FAINT_MARK_THRESHOLD: float = 0.008
    LOW_CONFIDENCE_THRESHOLD: float = 0.65  # below this the ballot is flagged for review
    # Ballot rules (printed on the paper):
    #  (kha) the X must stay inside the box  -> ink around the box voids the vote
    #  (ga)  a rubbed / scribbled mark is void -> a box that is mostly ink is void
    OUTSIDE_INK_THRESHOLD: float = 0.04  # ink ratio in the ring around a box that counts as 'outside'
    SMUDGE_THRESHOLD: float = 0.55       # ink ratio inside a box that counts as smudged / blacked out
    # Ballot paper numbers have 6 digits (000001 ... 000455, the wheels of the numbering
    # machine that stamps them on the papers); numbers are zero-padded to this width
    BALLOT_NUMBER_DIGITS: int = 6

    # --- Auth -------------------------------------------------------------
    JWT_SECRET_KEY: str = "icb-election-super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    ADMIN_DEFAULT_USERNAME: str = "admin"
    ADMIN_DEFAULT_PASSWORD: str = "admin123"

    # --- HTTP -------------------------------------------------------------
    CORS_ORIGINS: str = "*"             # comma separated list, or * for any origin
    SSE_REFRESH_INTERVAL: int = 2       # seconds between full dashboard refreshes
    LIVE_BALLOT_DISPLAY_SECONDS: int = 2  # default seconds between live-screen updates for a new election (set per election in Admin)
    PUBLISH_REPLAY_ENABLED: bool = True  # on Publish, replay every ballot from the first at the election's pace
    LOG_LEVEL: str = "INFO"

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _resolve(path_str: str) -> Path:
        path = Path(path_str).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    # ---------------------------------------------------------------------
    # Database file per election year
    # ---------------------------------------------------------------------
    _YEAR_TOKEN: ClassVar[re.Pattern] = re.compile(r"\{year\}", re.IGNORECASE)
    _database_year: int | None = None  # set from the admin panel / saved file

    @property
    def database_year(self) -> int:
        return self._database_year or self.ELECTION_YEAR or date.today().year

    @property
    def database_url_has_year(self) -> bool:
        return bool(self._YEAR_TOKEN.search(self.DATABASE_URL))

    def database_url_for(self, year: int) -> str:
        return self._resolve_sqlite_url(self._YEAR_TOKEN.sub(str(year), self.DATABASE_URL))

    @property
    def database_url(self) -> str:
        """DATABASE_URL for the current year, relative SQLite paths resolved against the project root."""
        return self.database_url_for(self.database_year)

    @staticmethod
    def sqlite_file(url: str) -> Path | None:
        """The database file behind a SQLite URL (None for other databases / in-memory)."""
        prefix = "sqlite+aiosqlite:///"
        if not url.startswith(prefix) or url[len(prefix):] in ("", ":memory:"):
            return None
        return Path(url[len(prefix):])

    @property
    def database_file(self) -> Path | None:
        return self.sqlite_file(self.database_url)

    @property
    def database_settings_path(self) -> Path:
        return self._resolve(self.DATABASE_SETTINGS_FILE)

    def load_database_year(self) -> None:
        try:
            year = json.loads(self.database_settings_path.read_text(encoding="utf-8")).get("year")
        except (OSError, ValueError, AttributeError):
            return
        if isinstance(year, int) and 2000 <= year <= 2100:
            self._database_year = year

    def save_database_year(self, year: int) -> None:
        self._database_year = year
        path = self.database_settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"year": year}, indent=2), encoding="utf-8")

    def _resolve_sqlite_url(self, url: str) -> str:
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix):
            raw = url[len(prefix):]
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                resolved = self._resolve(raw)
                resolved.parent.mkdir(parents=True, exist_ok=True)
                return prefix + resolved.as_posix()
            if raw and raw != ":memory:":
                Path(raw).parent.mkdir(parents=True, exist_ok=True)
        return url

    def _folder(self, value: str) -> Path:
        path = self._resolve(value)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def scanned_path(self) -> Path:
        return self._folder(self.SCANNED_FOLDER_PATH)

    @property
    def completed_path(self) -> Path:
        return self._folder(self.COMPLETED_FOLDER_PATH)

    @property
    def failed_path(self) -> Path:
        return self._folder(self.FAILED_FOLDER_PATH)

    @property
    def preview_path(self) -> Path:
        return self._folder(self.PREVIEW_FOLDER_PATH)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # ---------------------------------------------------------------------
    # Folders chosen in the admin panel
    # ---------------------------------------------------------------------
    FOLDER_KEYS: ClassVar[dict[str, str]] = {
        "scanned_folder": "SCANNED_FOLDER_PATH",
        "completed_folder": "COMPLETED_FOLDER_PATH",
        "failed_folder": "FAILED_FOLDER_PATH",
    }

    @property
    def folder_settings_path(self) -> Path:
        return self._resolve(self.FOLDER_SETTINGS_FILE)

    def load_folder_overrides(self) -> None:
        """Apply folders saved from the admin panel (ignored if the file is missing or broken)."""
        try:
            saved = json.loads(self.folder_settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, attr in self.FOLDER_KEYS.items():
            value = saved.get(key)
            if isinstance(value, str) and value.strip():
                setattr(self, attr, value.strip())

    def save_folder_overrides(self, folders: dict[str, str]) -> None:
        """Apply and persist new folders so they survive a restart."""
        for key, value in folders.items():
            setattr(self, self.FOLDER_KEYS[key], value)
        current = {key: str(self._resolve(getattr(self, attr))) for key, attr in self.FOLDER_KEYS.items()}
        path = self.folder_settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")


settings = Settings()
settings.load_folder_overrides()
settings.load_database_year()
