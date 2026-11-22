"""The three rules printed on the ballot."""

from app.services.ocr_service import ocr_service
from app.utils.sample_ballot import draw_ballot
from tests.conftest import make_ballot_pdf, template_positions
from tests.test_api import candidates_by_voter_no, upload
from tests.test_ocr import build_layout


def _marks(image):
    positions = template_positions()
    result = ocr_service.extract(image, build_layout(positions))
    assert result.layout_ok, result.warnings  # a box lost under an oversized X is recovered
    return {m.candidate_id: m for m in result.marks}


def test_rule_kha_x_outside_the_box_is_void():
    positions = template_positions()
    image = draw_ballot(positions, {"101"}, outside={"103"}, seed=1)
    marks = _marks(image)
    assert marks[1].kind == "x" and marks[1].void_reason is None
    assert marks[3].kind == "outside" and "kha" in marks[3].void_reason


def test_rule_ga_smudged_box_is_void():
    positions = template_positions()
    image = draw_ballot(positions, {"101"}, smudged={"105"}, seed=2)
    marks = _marks(image)
    assert marks[5].kind == "smudged" and "ga" in marks[5].void_reason


async def test_rules_end_to_end(client, auth, election):
    """One ballot breaking all three rules: only the clean marks are counted."""
    pdf = make_ballot_pdf({"101", "102", "107"}, "rules.pdf", seed=3, outside={"103"}, smudged={"105"})
    ballot = (await upload(client, auth, election["id"], pdf))[0]
    assert ballot["status"] == "needs_review"
    assert ballot["total_votes_extracted"] == 1  # only 107 counts
    warnings = " ".join(ballot["ocr_warnings"])
    assert "(ka)" in warnings and "(kha)" in warnings and "(ga)" in warnings

    counts = await candidates_by_voter_no(client, election["id"])
    assert counts["107"]["vote_count"] == 1
    for voter_no in ("101", "102", "103", "105"):
        assert counts[voter_no]["vote_count"] == 0

    detail = (await client.get(f"/api/ballots/{ballot['id']}", headers=auth)).json()
    reasons = {v["candidate_id"]: v["invalid_reason"] for v in detail["votes"]}
    assert sum(1 for r in reasons.values() if r and "(ka)" in r) == 2
    assert any(r and "(kha)" in r for r in reasons.values())
    assert any(r and "(ga)" in r for r in reasons.values())
