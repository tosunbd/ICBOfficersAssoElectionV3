"""Mark detection on synthetic ballots (no server involved)."""

import random

import pytest

from app.services.ocr_service import ocr_service
from app.utils.sample_ballot import draw_ballot, random_choices
from tests.conftest import template_positions


def build_layout(positions):
    layout, row, candidate_id, position_id = [], 0, 0, 0
    for pos in positions:
        position_id += 1
        for idx, cand in enumerate(pos["candidates"]):
            candidate_id += 1
            layout.append({
                "candidate_id": candidate_id, "position_id": position_id, "voter_no": cand["voter_no"],
                "row_index": row + idx // 2, "col_index": idx % 2,
            })
        row += -(-len(pos["candidates"]) // 2)
    return layout


@pytest.mark.parametrize("skew,noise", [(0, False), (1.0, True), (-1.5, False), (2.0, True)])
def test_marks_are_detected_exactly(skew, noise):
    positions = template_positions()
    layout = build_layout(positions)
    rng = random.Random(42)
    marked = random_choices(positions, rng)
    image = draw_ballot(positions, marked, skew_degrees=skew, noise=noise, seed=7)

    result = ocr_service.extract(image, layout)

    assert result.layout_ok, result.warnings
    assert result.boxes_detected == 30
    expected = {c["candidate_id"] for c in layout if c["voter_no"] in marked}
    detected = {m.candidate_id for m in result.marks if m.is_marked}
    assert detected == expected
    assert all(m.confidence >= 0.8 for m in result.marks if m.is_marked)


def test_empty_ballot_has_no_marks():
    positions = template_positions()
    layout = build_layout(positions)
    result = ocr_service.extract(draw_ballot(positions, set()), layout)
    assert result.boxes_detected == 30
    assert not any(m.is_marked for m in result.marks)


def test_real_template_scan_is_read():
    """The sample ballot image from the resources folder (unmarked)."""
    from pathlib import Path

    template = Path(__file__).resolve().parents[2] / "resources" / "ballot.jpg"
    if not template.exists():
        pytest.skip("resources/ballot.jpg not present")
    layout = build_layout(template_positions())
    result = ocr_service.process_file(template, layout)[0]
    assert result.boxes_detected == 30
    assert result.layout_ok
    assert not any(m.is_marked for m in result.marks)
