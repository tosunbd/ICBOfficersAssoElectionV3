"""Bulk ballot deletion and the Scanned / Completed folder picker."""

import json

from app.config import settings
from tests.conftest import TMP, make_ballot_pdf
from tests.test_api import candidates_by_voter_no, upload


def forget_files(ballots: list[dict]) -> None:
    """Deleting a ballot keeps its scan in Completed; remove it so later tests
    that expect Ballot_000001.pdf to be free are not affected."""
    for ballot in ballots:
        (settings.completed_path / ballot["pdf_filename"]).unlink(missing_ok=True)


async def test_bulk_delete_by_ids_rolls_back_votes(client, auth, election):
    first = (await upload(client, auth, election["id"], make_ballot_pdf({"101"}, "bulk_a.pdf")))[0]
    second = (await upload(client, auth, election["id"], make_ballot_pdf({"101"}, "bulk_b.pdf")))[0]
    assert (await candidates_by_voter_no(client, election["id"]))["101"]["vote_count"] == 2

    response = await client.post("/api/ballots/bulk-delete", headers=auth, json={"ballot_ids": [first["id"], second["id"]]})
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": 2}
    assert (await candidates_by_voter_no(client, election["id"]))["101"]["vote_count"] == 0
    listing = (await client.get(f"/api/ballots/?election_id={election['id']}", headers=auth)).json()
    assert listing["total"] == 0
    forget_files([first, second])


async def test_bulk_delete_all_matching(client, auth, election):
    created = []
    for name in ("all_a.pdf", "all_b.pdf", "all_c.pdf"):
        created += await upload(client, auth, election["id"], make_ballot_pdf({"103"}, name))
    response = await client.post("/api/ballots/bulk-delete", headers=auth,
                                 json={"election_id": election["id"], "all_matching": True})
    assert response.json() == {"deleted": 3}
    forget_files(created)
    assert (await client.post("/api/ballots/bulk-delete", headers=auth, json={})).status_code == 400


async def test_folder_browser_lists_subfolders(client, auth):
    (TMP / "browse" / "Alpha").mkdir(parents=True, exist_ok=True)
    (TMP / "browse" / "beta").mkdir(exist_ok=True)
    top = (await client.get("/api/admin/fs/browse", headers=auth)).json()
    assert top["path"] == "" and top["folders"]
    listing = (await client.get("/api/admin/fs/browse", headers=auth, params={"path": str(TMP / "browse")})).json()
    assert [f["name"] for f in listing["folders"]] == ["Alpha", "beta"]
    assert listing["parent"] == str(TMP.resolve())
    assert (await client.get("/api/admin/fs/browse", headers=auth, params={"path": "relative/x"})).status_code == 400
    assert (await client.get("/api/admin/fs/browse")).status_code in (401, 403)


async def test_update_folders_applies_and_persists(client, auth):
    old_scanned, old_completed = settings.SCANNED_FOLDER_PATH, settings.COMPLETED_FOLDER_PATH
    try:
        new_scanned, new_completed = TMP / "picked" / "In", TMP / "picked" / "Done"
        response = await client.put("/api/admin/folders", headers=auth, json={
            "scanned_folder": str(new_scanned), "completed_folder": str(new_completed),
        })
        assert response.status_code == 200, response.text
        assert response.json()["scanned_folder"] == str(new_scanned.resolve())
        assert new_scanned.is_dir() and new_completed.is_dir()
        saved = json.loads(settings.folder_settings_path.read_text(encoding="utf-8"))
        assert saved["completed_folder"] == str(new_completed.resolve())

        clash = await client.put("/api/admin/folders", headers=auth, json={"completed_folder": str(new_scanned)})
        assert clash.status_code == 400
        assert (await client.put("/api/admin/folders", headers=auth, json={"scanned_folder": "rel"})).status_code == 400
    finally:
        settings.save_folder_overrides({"scanned_folder": old_scanned, "completed_folder": old_completed})


async def test_database_year_switch_uses_a_fresh_file_and_keeps_logins(client, auth, election):
    info = (await client.get("/api/admin/database", headers=auth)).json()
    assert info["year"] == 2026 and info["per_year"] and info["file_name"] == "test2026.db"

    response = await client.put("/api/admin/database", headers=auth, json={"year": 2031})
    assert response.status_code == 200, response.text
    switched = response.json()
    assert switched["file_name"] == "test2031.db"
    assert {f["year"] for f in switched["files"]} == {2026, 2031}
    assert (TMP / "test2031.db").exists()
    assert json.loads((TMP / "database_settings.json").read_text())["year"] == 2031
    try:
        # the new file is empty, but the same admin account works there
        assert (await client.get("/api/elections/")).json() == []
        login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert login.status_code == 200
        actions = [e["action"] for e in (await client.get("/api/admin/audit-log", headers=auth)).json()]
        assert actions == ["login", "database_switch"]  # newest first; nothing from the 2026 file
    finally:
        assert (await client.put("/api/admin/database", headers=auth, json={"year": 2026})).status_code == 200
    ids = [e["id"] for e in (await client.get("/api/elections/")).json()]
    assert election["id"] in ids
    assert (await client.put("/api/admin/database", headers=auth, json={"year": 1999})).status_code == 422
