"""End-to-end API tests: setup -> upload ballots -> results -> review -> audit."""

import random

from app.config import settings
from app.services.ballot_processor import ballot_processor
from tests.conftest import make_ballot_pdf, template_positions


async def upload(client, auth, election_id, pdf_path):
    with open(pdf_path, "rb") as fh:
        response = await client.post(
            f"/api/ballots/upload?election_id={election_id}", headers=auth,
            files=[("files", (pdf_path.name, fh, "application/pdf"))],
        )
    assert response.status_code == 200, response.text
    return response.json()


async def candidates_by_voter_no(client, election_id):
    response = await client.get(f"/api/candidates/election/{election_id}")
    assert response.status_code == 200
    return {c["voter_no"]: c for c in response.json()}


# --------------------------------------------------------------------------
async def test_health_and_docs(client):
    assert (await client.get("/api/health")).json()["status"] == "healthy"
    assert (await client.get("/openapi.json")).status_code == 200


async def test_login_rejects_bad_password(client):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


async def test_collection_routes_answer_without_trailing_slash(client, auth, election):
    # A 307 to the slash URL would leave the UI proxy and drop the token.
    for method, url, body in (
        ("GET", "/api/elections", None),
        ("POST", "/api/elections", {"title": f"No Slash {random.randint(1000, 9999)}", "year": 2026, "total_voters": 10}),
        ("GET", f"/api/ballots?election_id={election['id']}", None),
    ):
        response = await client.request(method, url, headers=auth, json=body)
        assert response.status_code in (200, 201), (url, response.status_code, response.text)


async def test_protected_routes_need_token(client, election):
    assert (await client.get(f"/api/ballots/?election_id={election['id']}")).status_code in (401, 403)
    assert (await client.post("/api/elections/", json={"title": "x", "year": 2026})).status_code in (401, 403)


async def test_election_setup(client, auth, election):
    detail = (await client.get(f"/api/elections/{election['id']}")).json()
    assert len(detail["positions"]) == 13
    assert detail["positions"][12]["max_selections"] == 3
    assert detail["status"] == "active"
    candidates = await candidates_by_voter_no(client, election["id"])
    assert len(candidates) == 30
    # seeding twice is refused
    response = await client.post(f"/api/elections/{election['id']}/seed-positions", headers=auth)
    assert response.status_code == 400


async def test_only_one_active_election(client, auth, election):
    response = await client.post("/api/elections/", headers=auth, json={"title": "Second", "year": 2028})
    second = response.json()
    await client.put(f"/api/admin/election/{second['id']}/status?new_status=active", headers=auth)
    first = (await client.get(f"/api/elections/{election['id']}")).json()
    assert first["status"] == "completed"
    assert (await client.get("/api/dashboard/active")).json()["id"] == second["id"]


async def test_upload_ballot_counts_votes(client, auth, election):
    marked = {"101", "104", "105", "108", "109", "112", "113", "116", "117", "120", "121", "124", "125", "127", "130"}
    pdf = make_ballot_pdf(marked, "clean.pdf", seed=1)

    ballots = await upload(client, auth, election["id"], pdf)
    assert len(ballots) == 1
    ballot = ballots[0]
    assert ballot["status"] == "processed", ballot
    assert ballot["total_votes_extracted"] == 15
    assert ballot["boxes_detected"] == 30
    assert ballot["has_preview"]
    assert ballot["source"] == "upload"

    # File moved from Scanned to Completed and renamed with the ballot paper number
    assert not (settings.scanned_path / "clean.pdf").exists()
    assert ballot["ballot_paper_no"] == "000001"
    assert ballot["pdf_filename"] == "Ballot_000001.pdf"
    assert (settings.completed_path / "Ballot_000001.pdf").exists()

    candidates = await candidates_by_voter_no(client, election["id"])
    for voter_no, cand in candidates.items():
        assert cand["vote_count"] == (1 if voter_no in marked else 0), voter_no

    detail = (await client.get(f"/api/ballots/{ballot['id']}", headers=auth)).json()
    assert len(detail["votes"]) == 15
    assert all(v["is_valid"] for v in detail["votes"])

    preview = await client.get(f"/api/ballots/{ballot['id']}/preview", headers=auth)
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
    original = await client.get(f"/api/ballots/{ballot['id']}/file", headers=auth)
    assert original.status_code == 200


async def test_over_vote_is_flagged_and_not_counted(client, auth, election):
    # Two marks for President (max 1) and four marks for Executive Member (max 3)
    marked = {"101", "102", "105", "125", "126", "127", "128"}
    pdf = make_ballot_pdf(marked, "overvote.pdf", seed=2)
    ballot = (await upload(client, auth, election["id"], pdf))[0]

    assert ballot["status"] == "needs_review"
    assert ballot["total_votes_extracted"] == 1  # only 105 counts
    assert any("not counted" in w for w in ballot["ocr_warnings"])

    candidates = await candidates_by_voter_no(client, election["id"])
    assert candidates["105"]["vote_count"] == 1
    for voter_no in ("101", "102", "125", "126", "127", "128"):
        assert candidates[voter_no]["vote_count"] == 0

    stats = (await client.get(f"/api/dashboard/results/{election['id']}", headers=auth)).json()["stats"]
    assert stats["needs_review_ballots"] == 1
    assert stats["counted_ballots"] == 1


async def test_multi_page_pdf_creates_one_ballot_per_page(client, auth, election):
    from app.utils.sample_ballot import draw_ballot, save_pdf

    positions = template_positions()
    pages = [draw_ballot(positions, {"101", "103"}, seed=3), draw_ballot(positions, {"102", "104"}, seed=4)]
    pdf = save_pdf(pages, settings.scanned_path.parent / "generated" / "batch.pdf")

    ballots = await upload(client, auth, election["id"], pdf)
    assert [b["page_number"] for b in ballots] == [1, 2]
    assert [b["ballot_paper_no"] for b in ballots] == ["000001", "000002"]
    assert ballots[0]["pdf_filename"] == "Ballot_000001-000002.pdf"
    candidates = await candidates_by_voter_no(client, election["id"])
    assert {candidates[v]["vote_count"] for v in ("101", "102", "103", "104")} == {1}


async def test_scan_folder_processes_waiting_files(client, auth, election):
    make_ballot_pdf({"101"}, "waiting_a.pdf", seed=5)
    make_ballot_pdf({"102"}, "waiting_b.pdf", seed=6)
    for name in ("waiting_a.pdf", "waiting_b.pdf"):
        (settings.scanned_path / name).write_bytes((settings.scanned_path.parent / "generated" / name).read_bytes())
    (settings.scanned_path / "notes.txt").write_text("ignored")

    response = await client.post(f"/api/ballots/scan-folder?election_id={election['id']}", headers=auth)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["files_found"] == 2
    assert summary["files_processed"] == 2
    assert not list(settings.scanned_path.glob("*.pdf"))
    (settings.scanned_path / "notes.txt").unlink()


async def test_counting_pause_holds_files_until_start(client, auth, election):
    make_ballot_pdf({"101"}, "paused_a.pdf", seed=9)
    (settings.scanned_path / "paused_a.pdf").write_bytes((settings.scanned_path.parent / "generated" / "paused_a.pdf").read_bytes())
    pause_url = f"/api/admin/counting/{election['id']}/pause"

    assert (await client.put(f"{pause_url}?pause=true")).status_code == 401  # committee login needed
    response = await client.put(f"{pause_url}?pause=true", headers=auth)
    assert response.json()["status"] == "paused"
    results = (await client.get(f"/api/dashboard/results/{election['id']}")).json()
    assert results["counting_paused"] is True

    # nothing is read while paused: the file stays in the Scanned folder
    response = await client.post(f"/api/ballots/scan-folder?election_id={election['id']}", headers=auth)
    assert response.status_code == 409
    assert (settings.scanned_path / "paused_a.pdf").exists()

    # START reads the waiting files at once, without pressing Scan again
    response = await client.put(f"{pause_url}?pause=false", headers=auth)
    assert response.json()["status"] == "running"
    assert response.json()["scan_resumed"] is True
    await ballot_processor.wait_for_resumed_scan(election["id"])
    assert not (settings.scanned_path / "paused_a.pdf").exists()
    ballots = (await client.get(f"/api/ballots?election_id={election['id']}&per_page=200", headers=auth)).json()
    assert any(b["status"] != "error" and b["pdf_filename"].lower().endswith(".pdf") for b in ballots["ballots"])

    # nothing waiting: START again has nothing to resume
    await client.put(f"{pause_url}?pause=true", headers=auth)
    response = await client.put(f"{pause_url}?pause=false", headers=auth)
    assert response.json()["scan_resumed"] is False


async def test_scan_folder_refuses_a_second_scan_while_one_runs(client, auth, election):
    ballot_processor._folder_scans.add(election["id"])  # a scan (e.g. resumed by START) is running
    try:
        response = await client.post(f"/api/ballots/scan-folder?election_id={election['id']}", headers=auth)
        assert response.status_code == 409
        assert "already being read" in response.json()["detail"]
    finally:
        ballot_processor._folder_scans.discard(election["id"])


async def test_unreadable_file_becomes_error_ballot(client, auth, election):
    bad = settings.scanned_path.parent / "generated" / "broken.pdf"
    bad.write_bytes(b"this is not a pdf")
    ballot = (await upload(client, auth, election["id"], bad))[0]
    assert ballot["status"] == "error"
    assert ballot["error_message"]
    assert (settings.failed_path / "broken.pdf").exists()


async def test_review_replaces_votes_and_recount_agrees(client, auth, election):
    pdf = make_ballot_pdf({"101", "103"}, "review.pdf", seed=8)
    ballot = (await upload(client, auth, election["id"], pdf))[0]
    candidates = await candidates_by_voter_no(client, election["id"])
    positions = {c["voter_no"]: c["position_id"] for c in candidates.values()}

    # Admin decides the voter actually chose 102 (not 101) and keeps 103
    response = await client.put(f"/api/ballots/{ballot['id']}/review", headers=auth, json={
        "ballot_paper_no": "B-0042",
        "is_valid": True,
        "votes": [
            {"candidate_id": candidates["102"]["id"], "position_id": positions["102"], "is_valid": True},
            {"candidate_id": candidates["103"]["id"], "position_id": positions["103"], "is_valid": True},
        ],
    })
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["status"] == "reviewed"
    assert reviewed["ballot_paper_no"] == "B-0042"
    assert reviewed["total_votes_extracted"] == 2

    candidates = await candidates_by_voter_no(client, election["id"])
    assert candidates["101"]["vote_count"] == 0
    assert candidates["102"]["vote_count"] == 1
    assert candidates["103"]["vote_count"] == 1

    # Over-vote in a review is rejected
    response = await client.put(f"/api/ballots/{ballot['id']}/review", headers=auth, json={
        "votes": [
            {"candidate_id": candidates["101"]["id"], "position_id": positions["101"]},
            {"candidate_id": candidates["102"]["id"], "position_id": positions["102"]},
        ],
    })
    assert response.status_code == 400

    # Recount from vote records must match the counters
    before = {v: c["vote_count"] for v, c in candidates.items()}
    assert (await client.post(f"/api/admin/election/{election['id']}/recount", headers=auth)).status_code == 200
    after = {v: c["vote_count"] for v, c in (await candidates_by_voter_no(client, election["id"])).items()}
    assert before == after


async def test_reprocess_and_delete_keep_counts_consistent(client, auth, election):
    pdf = make_ballot_pdf({"101"}, "reprocess.pdf", seed=9)
    ballot = (await upload(client, auth, election["id"], pdf))[0]

    response = await client.post(f"/api/ballots/{ballot['id']}/reprocess", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["total_votes_extracted"] == 1
    assert (await candidates_by_voter_no(client, election["id"]))["101"]["vote_count"] == 1  # not doubled

    assert (await client.delete(f"/api/ballots/{ballot['id']}", headers=auth)).status_code == 204
    assert (await candidates_by_voter_no(client, election["id"]))["101"]["vote_count"] == 0
    assert (await client.get(f"/api/ballots/{ballot['id']}", headers=auth)).status_code == 404


async def test_dashboard_publish_gating(client, auth, election):
    await upload(client, auth, election["id"], make_ballot_pdf({"101"}, "gating.pdf", seed=10))

    public = (await client.get(f"/api/dashboard/results/{election['id']}")).json()
    assert public["dashboard_published"] is False
    assert public["results_visible"] is False
    assert public["positions"] == []
    assert public["stats"]["counted_ballots"] == 1  # progress is visible, numbers are not

    admin_view = (await client.get(f"/api/dashboard/results/{election['id']}", headers=auth)).json()
    assert admin_view["results_visible"] is True
    assert len(admin_view["positions"]) == 13
    president = admin_view["positions"][0]
    assert president["candidates"][0]["voter_no"] == "101"
    assert president["candidates"][0]["is_leading"] is True
    assert president["candidates"][0]["rank"] == 1

    await client.put(f"/api/admin/dashboard/{election['id']}/publish?publish=true", headers=auth)
    public = (await client.get(f"/api/dashboard/results/{election['id']}")).json()
    assert public["results_visible"] is True
    assert len(public["positions"]) == 13


async def test_live_event_follows_publish_pressed_during_a_scan(client, auth, election):
    """Scan pressed, THEN Publish: the scan's session loaded the election while it was
    unpublished.  The ballots it sends to the live screen must still carry the current
    state, or the screen drops to the "results will be published" page after each one."""
    from app import database
    from app.models import Election
    from app.services.events import notifier
    from app.services.vote_counter import vote_counter

    eid = election["id"]
    async with database.AsyncSessionLocal() as scan_session:  # the long-lived session of a folder scan
        # the Scan request keeps the election it looked up for as long as it runs
        held = await scan_session.get(Election, eid)
        assert held.dashboard_published is False
        before = await vote_counter.get_dashboard_data(scan_session, eid)
        assert before.results_visible is False

        await client.put(f"/api/admin/dashboard/{eid}/publish?publish=true", headers=auth)
        await client.put(f"/api/elections/{eid}", headers=auth, json={"ballot_display_seconds": 7})

        path = settings.scanned_path / "img_0001.pdf"
        make_ballot_pdf({"101"}, "img_0001.pdf", seed=31).replace(path)
        await ballot_processor.process_file(scan_session, path, eid, source="manual")

    event = notifier.latest("ballot", eid)
    assert event["results"]["results_visible"] is True
    assert len(event["results"]["positions"]) == 13
    assert event["display_seconds"] == 7


async def test_sse_stream_sends_update_and_paused(client, auth, election):
    """httpx's in-process transport cannot stream an endless response, so the
    generator behind the endpoint is exercised directly."""
    import json

    from app.routers.dashboard import dashboard_events

    events = dashboard_events(election["id"])
    first = await events.__anext__()
    assert first["event"] == "update"
    assert json.loads(first["data"])["election_id"] == election["id"]

    # A counted ballot arrives as its own event, followed by the refreshed totals
    await client.put(f"/api/admin/dashboard/{election['id']}/publish?publish=true", headers=auth)
    await events.__anext__()  # update caused by publishing
    await upload(client, auth, election["id"], make_ballot_pdf({"101", "103"}, "live.pdf", seed=11))
    ballot_event = await events.__anext__()
    assert ballot_event["event"] == "ballot"
    payload = json.loads(ballot_event["data"])
    assert payload["sequence_no"] == 1
    assert {v["voter_no"] for v in payload["votes"]} == {"101", "103"}
    assert payload["display_seconds"] > 0
    assert payload["results"]["positions"][0]["candidates"][0]["voter_no"] == "101"
    assert (await events.__anext__())["event"] == "update"
    preview = await client.get(f"/api/dashboard/ballots/{payload['ballot_id']}/preview")
    assert preview.status_code == 200

    # Pausing notifies the stream, which must emit `paused` without waiting for the timer
    await client.put(f"/api/admin/dashboard/{election['id']}/pause?pause=true", headers=auth)
    second = await events.__anext__()
    assert second["event"] == "paused"
    await events.aclose()

    # A screen that reconnects says which ballot it saw last and gets the ones it missed
    await client.put(f"/api/admin/dashboard/{election['id']}/pause?pause=false", headers=auth)
    missed = dashboard_events(election["id"], after=int(ballot_event["id"]) - 1)
    again = await missed.__anext__()
    assert again["event"] == "ballot" and again["id"] == ballot_event["id"]
    await missed.aclose()
    fresh = dashboard_events(election["id"])  # a new screen does not get the history
    assert (await fresh.__anext__())["event"] == "update"
    await fresh.aclose()

    # The HTTP endpoint itself answers with the SSE content type
    from app.routers.dashboard import stream_results
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    response = await stream_results(election["id"], Request(scope))
    assert response.media_type == "text/event-stream"


async def test_every_scanned_file_reaches_the_live_screen(client, auth, election, tmp_path):
    """Unreadable files and committee corrections are shown publicly too, and a
    screen opened mid-count can fetch the last ballot."""
    from app.services.events import notifier

    def ballot_events():
        return [data for _, kind, data in notifier.events_after(0)
                if kind == "ballot" and data["election_id"] == election["id"]]

    assert (await client.get(f"/api/dashboard/latest/{election['id']}")).json() is None
    await client.put(f"/api/admin/dashboard/{election['id']}/publish?publish=true", headers=auth)

    # a corrupt file: nothing counted, but the audience still sees it
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")
    await upload(client, auth, election["id"], broken)
    unreadable = ballot_events()[-1]
    assert unreadable["kind"] == "unreadable"
    assert unreadable["status"] == "error"
    assert "Could not read" in unreadable["error_message"]
    assert unreadable["votes"] == []

    # a counted ballot, then the committee's correction of it
    await upload(client, auth, election["id"], make_ballot_pdf({"101"}, "shown.pdf", seed=12))
    counted = ballot_events()[-1]
    assert counted["kind"] == "counted"
    latest = (await client.get(f"/api/dashboard/latest/{election['id']}")).json()
    assert latest["ballot_id"] == counted["ballot_id"]

    candidates = await candidates_by_voter_no(client, election["id"])
    response = await client.put(f"/api/ballots/{counted['ballot_id']}/review", headers=auth, json={
        "is_valid": True,
        "votes": [{"candidate_id": candidates["102"]["id"], "position_id": candidates["102"]["position_id"], "is_valid": True}],
    })
    assert response.status_code == 200, response.text
    reviewed = ballot_events()[-1]
    assert reviewed["kind"] == "reviewed"
    assert {v["voter_no"] for v in reviewed["votes"]} == {"102"}

    # nothing is offered while the screen is paused
    await client.put(f"/api/admin/dashboard/{election['id']}/pause?pause=true", headers=auth)
    assert (await client.get(f"/api/dashboard/latest/{election['id']}")).json() is None


async def test_publish_replays_the_count_ballot_by_ballot(client, auth, election, tmp_path, monkeypatch):
    """Publishing restarts the public screen from zero and shows each scanned
    file in order, with the totals as they stood after it."""
    from app.services.events import notifier
    from app.services.live_replay import live_replay

    eid = election["id"]
    await upload(client, auth, eid, make_ballot_pdf({"101"}, "r1.pdf", seed=21))
    await upload(client, auth, eid, make_ballot_pdf({"103"}, "r2.pdf", seed=22))
    broken = tmp_path / "r3.pdf"
    broken.write_bytes(b"not a pdf")
    await upload(client, auth, eid, broken)
    await upload(client, auth, eid, make_ballot_pdf({"101", "104"}, "r4.pdf", seed=23))

    monkeypatch.setattr(settings, "PUBLISH_REPLAY_ENABLED", True)
    assert election["ballot_display_seconds"] == settings.LIVE_BALLOT_DISPLAY_SECONDS
    response = await client.put(f"/api/elections/{eid}", headers=auth, json={"ballot_display_seconds": 10})
    assert response.json()["ballot_display_seconds"] == 10
    response = await client.put(f"/api/admin/dashboard/{eid}/publish?publish=true", headers=auth)
    assert response.json()["replay"] == {"running": True, "shown": 0, "total": 0, "seconds": 10}
    assert (await client.get("/api/dashboard/active")).json()["live_display_seconds"] == 10
    live_replay.start(eid, 10, background=False)  # step it by hand instead of waiting 10 s per ballot
    seq = notifier.last_seq

    async def public_votes():
        data = (await client.get(f"/api/dashboard/results/{eid}")).json()
        return data["stats"]["counted_ballots"], {
            c["voter_no"]: c["vote_count"] for p in data["positions"] for c in p["candidates"] if c["vote_count"]
        }

    assert await public_votes() == (0, {})  # starts from zero
    admin = (await client.get(f"/api/dashboard/results/{eid}", headers=auth)).json()
    assert admin["stats"]["counted_ballots"] == 3  # the committee still sees the real totals

    # a ballot counted during the replay is not sent live; the replay shows it last
    await upload(client, auth, eid, make_ballot_pdf({"103"}, "r5.pdf", seed=24))
    assert not any(kind == "ballot" for _, kind, _ in notifier.events_after(seq))

    expected = [
        ("counted", 1, {"101": 1}),
        ("counted", 2, {"101": 1, "103": 1}),
        ("unreadable", 2, {"101": 1, "103": 1}),
        ("counted", 3, {"101": 2, "103": 1, "104": 1}),
        ("counted", 4, {"101": 2, "103": 2, "104": 1}),
    ]
    for position, (kind, counted, votes) in enumerate(expected, start=1):
        assert await live_replay.advance(eid) is True
        event = [d for _, k, d in notifier.events_after(seq) if k == "ballot"][-1]
        assert event["kind"] == kind
        assert event["replay"] == {"position": position, "total": 5}
        assert event["results"]["replay"] == event["replay"]
        assert event["display_seconds"] == 10
        shown = {c["voter_no"]: c["vote_count"] for p in event["results"]["positions"] for c in p["candidates"] if c["vote_count"]}
        assert shown == votes
        assert event["results"]["stats"]["counted_ballots"] == counted
        assert await public_votes() == (counted, votes)

    assert await live_replay.advance(eid) is False  # nothing left
    live_replay.stop(eid)
    final = await candidates_by_voter_no(client, eid)
    assert {n: final[n]["vote_count"] for n in ("101", "103", "104")} == {"101": 2, "103": 2, "104": 1}
    assert await public_votes() == (4, {"101": 2, "103": 2, "104": 1})
    assert (await client.get(f"/api/dashboard/results/{eid}")).json()["replay"] is None

    # skip and unpublish both end a replay
    assert (await client.post(f"/api/admin/dashboard/{eid}/replay", headers=auth)).json()["running"] is True
    assert (await client.delete(f"/api/admin/dashboard/{eid}/replay", headers=auth)).json()["running"] is False
    live_replay.start(eid, 10, background=False)
    await client.put(f"/api/admin/dashboard/{eid}/publish?publish=false", headers=auth)
    assert live_replay.is_running(eid) is False


async def test_audit_log_and_system_status(client, auth, election):
    log = (await client.get("/api/admin/audit-log?limit=20", headers=auth)).json()
    actions = {entry["action"] for entry in log}
    assert {"login", "election_create", "positions_seed", "election_status_change"} <= actions
    assert all(entry["username"] == "admin" for entry in log if entry["admin_user_id"])

    system = (await client.get("/api/admin/system", headers=auth)).json()
    assert system["auto_process_enabled"] is False
    assert system["active_election_id"] == election["id"]


async def test_change_password_roundtrip(client, auth):
    bad = await client.put("/api/auth/change-password", headers=auth,
                           json={"current_password": "nope", "new_password": "secret123"})
    assert bad.status_code == 400
    ok = await client.put("/api/auth/change-password", headers=auth,
                          json={"current_password": "admin123", "new_password": "secret123"})
    assert ok.status_code == 200
    assert (await client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})).status_code == 200
    # restore for the other tests
    token = (await client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})).json()["access_token"]
    await client.put("/api/auth/change-password", headers={"Authorization": f"Bearer {token}"},
                     json={"current_password": "secret123", "new_password": "admin123"})


async def test_candidate_crud(client, auth, election):
    detail = (await client.get(f"/api/elections/{election['id']}")).json()
    president = detail["positions"][0]
    created = await client.post("/api/candidates/", headers=auth, json={
        "position_id": president["id"], "election_id": election["id"],
        "voter_no": "199", "name_en": "Extra Candidate", "display_order": 2,
    })
    assert created.status_code == 201
    cid = created.json()["id"]
    updated = await client.put(f"/api/candidates/{cid}", headers=auth, json={"name_bn": "অতিরিক্ত"})
    assert updated.json()["name_bn"] == "অতিরিক্ত"
    wrong = await client.post("/api/candidates/", headers=auth, json={
        "position_id": president["id"], "election_id": election["id"] + 999, "voter_no": "1", "name_en": "x",
    })
    assert wrong.status_code == 400
    assert (await client.delete(f"/api/candidates/{cid}", headers=auth)).status_code == 204
    assert (await client.get(f"/api/candidates/{cid}")).status_code == 404
