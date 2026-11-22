"""Test fixtures.

Every test session gets its own temporary data folder and SQLite file, so
tests never touch the real `data/` directory.  The environment must be set
BEFORE `app.config` is imported, which is why this happens at module level.
"""

import os
import random
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="icb-election-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{(TMP / 'test{Year}.db').as_posix()}",
    "ELECTION_YEAR": "2026",
    "DATABASE_SETTINGS_FILE": str(TMP / "database_settings.json"),
    "SCANNED_FOLDER_PATH": str(TMP / "Scanned"),
    "COMPLETED_FOLDER_PATH": str(TMP / "Completed"),
    "FAILED_FOLDER_PATH": str(TMP / "Failed"),
    "PREVIEW_FOLDER_PATH": str(TMP / "Previews"),
    "AUTO_PROCESS_ENABLED": "false",
    "PUBLISH_REPLAY_ENABLED": "false",  # tests that need the replay switch it on themselves
    "ADMIN_DEFAULT_USERNAME": "admin",
    "ADMIN_DEFAULT_PASSWORD": "admin123",
    "JWT_SECRET_KEY": "test-secret",
    "FOLDER_SETTINGS_FILE": str(TMP / "folder_settings.json"),
})

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app, create_default_admin  # noqa: E402
from app.utils.sample_ballot import draw_ballot, save_pdf  # noqa: E402

POSITION_NAMES = [
    "President", "Vice President", "General Secretary", "Asst. General Secretary", "Treasurer",
    "Organizing Secretary", "Office Secretary", "Publication Secretary", "Cultural Secretary",
    "Drama Secretary", "Sports Secretary", "Hospitality Secretary", "Executive Member",
]


def template_positions() -> list[dict]:
    """The 13 ICB positions with the 30 template candidates (voter no 101-130)."""
    positions, voter_no = [], 101
    for index, name in enumerate(POSITION_NAMES):
        count = 6 if index == 12 else 2
        positions.append({
            "name": name,
            "max_selections": 3 if index == 12 else 1,
            "candidates": [{"voter_no": str(voter_no + k), "name": f"Candidate {voter_no + k}"} for k in range(count)],
        })
        voter_no += count
    return positions


def make_ballot_pdf(marked: set[str], name: str, **kwargs) -> Path:
    image = draw_ballot(template_positions(), marked, **kwargs)  # kwargs: seed, skew_degrees, outside, smudged ...
    return save_pdf([image], TMP / "generated" / name)


@pytest.fixture(scope="session", autouse=True)
async def _database():
    await init_db()
    await create_default_admin()
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth(client):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def election(client, auth):
    """A fresh election with the 13 positions and 30 template candidates."""
    response = await client.post("/api/elections/", headers=auth, json={
        "title": f"Test Election {random.randint(1000, 9999)}",
        "title_bn": "পরীক্ষামূলক নির্বাচন",
        "year": 2026,
        "total_voters": 100,
    })
    assert response.status_code == 201, response.text
    election = response.json()
    response = await client.post(
        f"/api/elections/{election['id']}/seed-positions?with_template_candidates=true", headers=auth
    )
    assert response.status_code == 200, response.text
    response = await client.put(f"/api/admin/election/{election['id']}/status?new_status=active", headers=auth)
    assert response.status_code == 200, response.text
    return election


@pytest.fixture
def data_dir():
    return settings
