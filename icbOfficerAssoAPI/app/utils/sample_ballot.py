"""Generate synthetic ballot images/PDFs that mimic the printed ICB ballot.

Used by the automated tests and by `scripts/make_sample_ballots.py` so that
the whole pipeline can be exercised without a scanner.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Page geometry (A4 at 200 DPI)
PAGE_W, PAGE_H = 1654, 2339
TABLE_LEFT, TABLE_RIGHT = 119, 1575
TABLE_TOP = 250
# Ballot of 11-11-2026: candidate 1 | box 1 | post name | candidate 2 | box 2
COL_EDGES = [TABLE_LEFT, 439, 677, 1002, 1385, TABLE_RIGHT]
HALVES = [(COL_EDGES[0], COL_EDGES[1], COL_EDGES[2]), (COL_EDGES[3], COL_EDGES[4], COL_EDGES[5])]  # (name x0, box x0, box x1)
HEADER_H = 90
ROW_H = 95
BOX_W, BOX_H = 120, 78  # same proportions as the printed ballot


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def ballot_rows(positions: list[dict], columns: int = 2) -> list[list[dict | None]]:
    """Lay candidates out exactly like `BallotProcessor.build_layout` does."""
    rows: list[list[dict | None]] = []
    for pos in positions:
        cands = pos["candidates"]
        for i in range(0, len(cands), columns):
            chunk = list(cands[i: i + columns])
            chunk += [None] * (columns - len(chunk))
            rows.append(chunk)
    return rows


def draw_ballot(
    positions: list[dict],
    marked: set[str],
    *,
    skew_degrees: float = 0.0,
    noise: bool = False,
    seed: int | None = None,
    ballot_no: str | None = None,
    outside: set[str] | None = None,
    smudged: set[str] | None = None,
) -> Image.Image:
    """Draw a ballot.

    positions: [{"name": str, "candidates": [{"voter_no": str, "name": str}, ...]}]
    marked:    voter_no values to mark with an X inside the box
    outside:   voter_no values whose X is drawn crossing the box border (rule kha violation)
    smudged:   voter_no values whose box is scribbled solid (rule ga violation)
    ballot_no: printed in the ballot-number box at the top right
    """
    outside = outside or set()
    smudged = smudged or set()
    rng = random.Random(seed)
    img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(img)
    title_font, cell_font, small_font = _font(34), _font(26), _font(22)

    draw.text((TABLE_LEFT + 40, 120), "ICB Officers' Association Election", fill="black", font=title_font)
    # Ballot paper number box (top right, outside the table) – must be ignored by OCR
    draw.text((1180, 128), "Ballot No", fill="black", font=small_font)
    draw.rectangle([1330, 110, 1470, 175], outline="black", width=3)
    if ballot_no:
        draw.text((1348, 124), str(ballot_no), fill="black", font=cell_font)

    rows = ballot_rows(positions)
    table_bottom = TABLE_TOP + HEADER_H + ROW_H * len(rows)

    # Grid: outer frame, the post-name column and the candidate rows.  Rows of a post
    # with several candidate rows (Executive Member) share one merged post cell.
    draw.rectangle([TABLE_LEFT, TABLE_TOP, TABLE_RIGHT, table_bottom], outline="black", width=4)
    for x in (COL_EDGES[2], COL_EDGES[3]):
        draw.line([(x, TABLE_TOP), (x, table_bottom)], fill="black", width=3)
    for x in (COL_EDGES[1], COL_EDGES[4]):
        draw.line([(x, TABLE_TOP + HEADER_H), (x, table_bottom)], fill="black", width=3)
    draw.line([(TABLE_LEFT, TABLE_TOP + HEADER_H), (TABLE_RIGHT, TABLE_TOP + HEADER_H)], fill="black", width=3)

    for x0, x1, text in ((COL_EDGES[0], COL_EDGES[2], "Candidate"), (COL_EDGES[2], COL_EDGES[3], "Position"),
                         (COL_EDGES[3], COL_EDGES[5], "Candidate")):
        draw.text((x0 + 12, TABLE_TOP + 28), text, fill="black", font=cell_font)

    # Rows
    y = TABLE_TOP + HEADER_H
    row_iter = iter(rows)
    for pos in positions:
        n_rows = max(1, -(-len(pos["candidates"]) // 2))
        first_y = y
        for i in range(n_rows):
            row = next(row_iter)
            for (name_x0, box_x0, box_x1), cand in zip(HALVES, row):
                if cand is None:
                    continue
                draw.text((name_x0 + 12, y + 14), cand["voter_no"], fill="black", font=cell_font)
                draw.text((name_x0 + 12, y + 50), cand["name"], fill="black", font=small_font)
                bx = (box_x0 + box_x1) // 2 - BOX_W // 2
                by = y + (ROW_H - BOX_H) // 2
                draw.rectangle([bx, by, bx + BOX_W, by + BOX_H], outline="black", width=3)
                jitter = lambda: rng.randint(-6, 6)  # noqa: E731
                if cand["voter_no"] in smudged:
                    draw.rectangle([bx + 4, by + 4, bx + BOX_W - 4, by + BOX_H - 4], fill="black")
                elif cand["voter_no"] in outside:
                    # X drawn too big: strokes cross the border and stick out of the box
                    over = 34
                    draw.line([(bx - over, by - over // 2), (bx + BOX_W + over, by + BOX_H + over // 2)], fill="black", width=6)
                    draw.line([(bx + BOX_W + over, by - over // 2), (bx - over, by + BOX_H + over // 2)], fill="black", width=6)
                elif cand["voter_no"] in marked:
                    pad = 10
                    draw.line([(bx + pad + jitter(), by + pad + jitter()), (bx + BOX_W - pad + jitter(), by + BOX_H - pad + jitter())], fill="black", width=6)
                    draw.line([(bx + BOX_W - pad + jitter(), by + pad + jitter()), (bx + pad + jitter(), by + BOX_H - pad + jitter())], fill="black", width=6)
            y += ROW_H
            last = i == n_rows - 1
            draw.line([(TABLE_LEFT, y), (COL_EDGES[2], y)], fill="black", width=3)
            draw.line([(COL_EDGES[3], y), (TABLE_RIGHT, y)], fill="black", width=3)
            if last:
                draw.line([(COL_EDGES[2], y), (COL_EDGES[3], y)], fill="black", width=3)
        draw.text((COL_EDGES[2] + 12, (first_y + y) // 2 - 12), pos["name"], fill="black", font=small_font)

    draw.text((TABLE_LEFT, table_bottom + 40), "Instructions: put an X in the box next to your candidate.", fill="black", font=small_font)

    if noise:
        px = img.load()
        for _ in range(4000):
            px[rng.randrange(PAGE_W), rng.randrange(PAGE_H)] = (rng.randint(0, 120),) * 3
    if skew_degrees:
        img = img.rotate(skew_degrees, resample=Image.BICUBIC, expand=False, fillcolor="white")
    return img


def save_pdf(images: list[Image.Image], dest: Path, dpi: int = 200) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    first, rest = images[0], images[1:]
    first.save(dest, "PDF", resolution=dpi, save_all=bool(rest), append_images=rest)
    return dest


def random_choices(positions: list[dict], rng: random.Random) -> set[str]:
    """Pick a valid random selection for each position."""
    marked: set[str] = set()
    for pos in positions:
        k = min(pos.get("max_selections", 1), len(pos["candidates"]))
        if rng.random() < 0.1:  # occasional abstention
            continue
        for cand in rng.sample(pos["candidates"], k):
            marked.add(cand["voter_no"])
    return marked
