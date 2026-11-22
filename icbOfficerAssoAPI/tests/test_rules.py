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


def test_unclear_mark_is_read_as_a_touched_box():
    positions = template_positions()
    marks = _marks(draw_ballot(positions, {"103"}, faint={"101"}, seed=4))
    assert marks[1].is_marked and marks[1].kind == "faint" and marks[1].void_reason is None
    assert not marks[2].is_marked and marks[2].density == 0
    assert marks[3].kind == "x"


async def test_unclear_mark_counts_alone_and_voids_when_both_boxes_are_touched(client, auth, election):
    """101/102 share a post, so do 103/104 and 105/106.
    101 unclear, 102 empty          -> 101 gets the vote
    103 clear X, 104 unclear        -> both boxes touched: no vote for the post
    105 X outside the box, 106 X    -> both boxes touched: no vote for the post"""
    pdf = make_ballot_pdf({"103", "106", "107"}, "unclear.pdf", seed=5, faint={"101", "104"}, outside={"105"})
    ballot = (await upload(client, auth, election["id"], pdf))[0]
    assert ballot["status"] == "needs_review"  # the committee looks at every unclear mark
    assert ballot["total_votes_extracted"] == 2  # 101 and 107

    counts = await candidates_by_voter_no(client, election["id"])
    assert counts["101"]["vote_count"] == 1
    assert counts["107"]["vote_count"] == 1
    for voter_no in ("102", "103", "104", "105", "106"):
        assert counts[voter_no]["vote_count"] == 0


def test_small_and_broken_x_marks_are_accepted():
    """The committee's sample of accepted votes: a small X with one short arm, an X with a
    broken arm, and a light X whose strokes do not meet.  Thin or thick pen, each is a vote."""
    import pytest
    from PIL import ImageDraw

    positions = template_positions()
    box = {cid: m.box for cid, m in _marks(draw_ballot(positions, set())).items()}
    strokes = {
        1: [(-0.20, 0.28, 0.20, -0.30), (-0.05, -0.02, 0.14, 0.26)],
        3: [(-0.22, 0.30, 0.20, -0.30), (-0.16, -0.20, -0.06, -0.06), (0.02, 0.10, 0.14, 0.26)],
        5: [(-0.22, 0.32, -0.06, 0.08), (0.04, -0.10, 0.12, -0.30), (-0.16, -0.18, -0.08, -0.08), (0.06, 0.12, 0.26, 0.24)],
    }
    for width, grey in ((4, 0), (2, 110)):
        image = draw_ballot(positions, set())
        draw = ImageDraw.Draw(image)
        for cid, lines in strokes.items():
            b = box[cid]
            cx, cy = b.x + b.w / 2, b.y + b.h / 2
            for x0, y0, x1, y1 in lines:
                draw.line([(cx + x0 * b.w, cy + y0 * b.h), (cx + x1 * b.w, cy + y1 * b.h)], fill=(grey,) * 3, width=width)
        marks = _marks(image)
        for cid in strokes:
            assert marks[cid].is_marked and marks[cid].void_reason is None, (width, cid, marks[cid])
        assert [cid for cid, m in marks.items() if m.is_marked] == pytest.approx(sorted(strokes))
