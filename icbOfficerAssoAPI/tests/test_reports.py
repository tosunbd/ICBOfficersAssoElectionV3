"""Admin -> Reports: result summary and the ballot-by-ballot tally."""

from tests.conftest import make_ballot_pdf
from tests.test_api import candidates_by_voter_no, upload


async def test_report_needs_login(client, election):
    response = await client.get(f"/api/reports/{election['id']}")
    assert response.status_code == 401


async def test_summary_matches_ballot_tally(client, auth, election):
    # President 101 v 102: 2-1 · Vice President 103 v 104: 1-2 · General Secretary 105 v 106: 1-1 (tie)
    for marks, name, seed in (
        ({"101", "103", "105", "125", "126", "127"}, "report_a.pdf", 21),
        ({"101", "104", "125", "126", "128"}, "report_b.pdf", 22),
        ({"102", "104", "106", "125"}, "report_c.pdf", 23),
    ):
        ballot = (await upload(client, auth, election["id"], make_ballot_pdf(marks, name, seed=seed)))[0]
        assert ballot["status"] == "processed", ballot

    response = await client.get(f"/api/reports/{election['id']}", headers=auth)
    assert response.status_code == 200, response.text
    report = response.json()

    assert [b["serial"] for b in report["ballots"]] == [1, 2, 3]
    assert report["manual_ballots"] == 0
    assert report["total_votes"] == 15

    # every candidate's total is the column sum of the 1/0 tally
    column_sums: dict[int, int] = {}
    for ballot in report["ballots"]:
        for candidate_id in ballot["candidate_ids"]:
            column_sums[candidate_id] = column_sums.get(candidate_id, 0) + 1
    by_voter_no = {}
    for position in report["positions"]:
        for c in position["candidates"]:
            assert c["votes"] == column_sums.get(c["candidate_id"], 0), c
            by_voter_no[c["voter_no"]] = c
    # ... and the same as the counters behind the live dashboard
    dashboard = (await client.get(f"/api/dashboard/results/{election['id']}", headers=auth)).json()
    for position in dashboard["positions"]:
        for c in position["candidates"]:
            assert c["vote_count"] == by_voter_no[c["voter_no"]]["votes"], c

    assert by_voter_no["101"]["outcome"] == "elected" and by_voter_no["102"]["outcome"] == ""
    assert by_voter_no["104"]["outcome"] == "elected" and by_voter_no["103"]["outcome"] == ""
    assert by_voter_no["105"]["outcome"] == "tie" and by_voter_no["106"]["outcome"] == "tie"
    # Executive Member, 3 seats: 125 (3), 126 (2), then 127 and 128 tie on 1 for the last seat
    assert by_voter_no["125"]["outcome"] == "elected" and by_voter_no["126"]["outcome"] == "elected"
    assert by_voter_no["127"]["outcome"] == "tie" and by_voter_no["128"]["outcome"] == "tie"
    assert by_voter_no["129"]["outcome"] == "" and by_voter_no["107"]["outcome"] == ""  # no votes, not elected
    assert by_voter_no["101"]["percentage"] == 66.67


async def test_manual_file_counts_in_the_totals(client, auth, election, tmp_path):
    """An unreadable file whose votes the Election Commission enters by hand is a
    manual file: it counts like any other ballot.  Nothing rejects a whole ballot."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")
    ballot = (await upload(client, auth, election["id"], broken))[0]
    assert ballot["status"] == "error"

    report = (await client.get(f"/api/reports/{election['id']}", headers=auth)).json()
    assert report["ballots"] == [] and report["stats"]["error_ballots"] == 1

    candidates = await candidates_by_voter_no(client, election["id"])
    response = await client.put(
        f"/api/ballots/{ballot['id']}/review", headers=auth,
        json={"is_valid": False,  # ignored: a ballot is never rejected
              "votes": [{"candidate_id": candidates[v]["id"], "position_id": candidates[v]["position_id"]} for v in ("101", "125")]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reviewed" and response.json()["is_valid"] is True

    report = (await client.get(f"/api/reports/{election['id']}", headers=auth)).json()
    row = next(b for b in report["ballots"] if b["ballot_id"] == ballot["id"])
    assert row["status"] == "reviewed" and len(row["candidate_ids"]) == 2
    assert report["manual_ballots"] == 1 and report["total_votes"] == 2
    votes = {c["voter_no"]: c["votes"] for p in report["positions"] for c in p["candidates"]}
    assert votes["101"] == 1 and votes["125"] == 1


async def test_panel_side_follows_the_ballot_layout(client, auth, election):
    """Panel Votes: two candidates to a row, so they alternate left, right."""
    report = (await client.get(f"/api/reports/{election['id']}", headers=auth)).json()
    panel = {c["voter_no"]: c["panel"] for p in report["positions"] for c in p["candidates"]}
    assert panel["101"] == "left" and panel["102"] == "right"
    # Executive Member: three rows of two
    assert [panel[str(n)] for n in range(125, 131)] == ["left", "right"] * 3
    assert sum(1 for side in panel.values() if side == "left") == 15


async def test_null_votes_list_every_mark_not_counted(client, auth, election, tmp_path):
    # two marks for President (max 1), four for Executive Member (max 3); only 105 counts
    pdf = make_ballot_pdf({"101", "102", "105", "125", "126", "127", "128"}, "null_votes.pdf", seed=2)
    ballot = (await upload(client, auth, election["id"], pdf))[0]
    broken = tmp_path / "null_broken.pdf"
    broken.write_bytes(b"this is not a pdf")
    unread = (await upload(client, auth, election["id"], broken))[0]

    report = (await client.get(f"/api/reports/{election['id']}", headers=auth)).json()
    row = next(b for b in report["ballots"] if b["ballot_id"] == ballot["id"])
    by_voter_no = {c["voter_no"]: c["candidate_id"] for p in report["positions"] for c in p["candidates"]}
    assert {v["candidate_id"] for v in row["void"]} == {by_voter_no[v] for v in ("101", "102", "125", "126", "127", "128")}
    assert all("Rule (ka)" in v["reason"] for v in row["void"])
    assert row["void_marks"] == 6 and report["void_marks"] == 6 and report["total_votes"] == 1
    assert [f["ballot_id"] for f in report["unread_files"]] == [unread["id"]]
    assert report["unread_files"][0]["reason"]
