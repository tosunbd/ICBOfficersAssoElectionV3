r"""Create the manual test set in "Sample Ballots": 15 PDFs + 15 images.

Run from the icbOfficerAssoAPI folder:

    .venv\Scripts\python scripts\make_test_ballots.py

Writes (in <project>/Sample Ballots):
    candidates.csv          30 candidates -> Admin -> Candidates -> Import CSV
    pdfs/Ballot_0001..0015.pdf    scanned-PDF ballots
    images/Ballot_0016..0030.jpg  image ballots, deliberately varied like real scans:
                                  72/150/200/300 DPI, skewed, upside down, sideways
    answer_key.csv          what every ballot marks and whether each mark counts
    expected_tally.csv      correct totals: PDFs only, images only, both
    README.txt              the test procedure

In each set the last three ballots break one printed rule each:
    13 / 28  rule (ka)  two X for President (only one allowed) -> President not counted
    14 / 29  rule (kha) the Vice President X crosses the box border -> void
    15 / 30  rule (ga)  the General Secretary box is scribbled over -> void
Every other mark on those ballots still counts.

The layout matches the candidate list (2 per post, 6 for Executive Member),
so import candidates.csv before processing.  The random choices use a fixed
seed: running the script again produces the same ballots.
"""

from __future__ import annotations

import csv
import random
import sys
from collections import Counter
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from PIL import Image  # noqa: E402

from app.routers.elections import DEFAULT_POSITIONS  # noqa: E402
from app.utils.sample_ballot import draw_ballot, random_choices, save_pdf  # noqa: E402

ROOT = API_DIR.parent
OUT = ROOT / "Sample Ballots"
CANDIDATES_CSV = ROOT / "resources" / "esource" / "candidates.csv"
SEED = 2026
PER_SET = 15

# How each image ballot is "scanned": (dpi, rotation in degrees, note)
IMAGE_VARIANTS = [
    (200, 0, "200 DPI"),
    (200, 0, "200 DPI"),
    (300, 0, "300 DPI"),
    (150, 0, "150 DPI"),
    (72, 0, "72 DPI (PDF exported to JPG)"),
    (200, 180, "scanned upside down"),
    (200, 90, "scanned sideways"),
    (200, 0, "200 DPI"),
    (300, 0, "300 DPI"),
    (200, 0, "200 DPI"),
    (150, 0, "150 DPI"),
    (200, 0, "200 DPI"),
    (200, 0, "200 DPI"),
    (200, 0, "200 DPI"),
    (200, 0, "200 DPI"),
]
DRAW_DPI = 200  # draw_ballot renders an A4 page at 200 DPI


def load_positions() -> list[dict]:
    with CANDIDATES_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    positions = []
    for pos in DEFAULT_POSITIONS:
        cands = [
            {"voter_no": r["voter_no"], "name": r["name_en"], "name_bn": r["name_bn"]}
            for r in rows if int(r["post_no"]) == pos["position_order"]
        ]
        positions.append({
            "post_no": pos["position_order"], "name": pos["name_en"], "name_bn": pos["name_bn"],
            "max_selections": pos["max_selections"], "candidates": cands,
        })
    return positions


def make_ballot(positions: list[dict], rule: str | None, rng: random.Random):
    """Returns (image, marked, outside, smudged)."""
    marked = random_choices(positions, rng)
    outside: set[str] = set()
    smudged: set[str] = set()
    post = {p["post_no"]: [c["voter_no"] for c in p["candidates"]] for p in positions}
    if rule == "ka":
        marked.update(post[1])                      # both President candidates
    elif rule == "kha":
        marked.difference_update(post[2])
        outside.add(post[2][0])                     # Vice President X over the border
    elif rule == "ga":
        marked.difference_update(post[3])
        smudged.add(post[3][1])                     # General Secretary box scribbled
    return marked, outside, smudged


def main() -> None:
    positions = load_positions()
    rng = random.Random(SEED)
    (OUT / "pdfs").mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    for folder in (OUT / "pdfs", OUT / "images"):
        for old in folder.iterdir():
            if old.is_file():
                old.unlink()

    rules = {PER_SET - 2: "ka", PER_SET - 1: "kha", PER_SET: "ga"}  # last three of each set
    key_rows: list[dict] = []
    tally = {"pdf": Counter(), "image": Counter()}

    for n in range(1, 2 * PER_SET + 1):
        kind = "pdf" if n <= PER_SET else "image"
        index = (n - 1) % PER_SET + 1
        rule = rules.get(index)
        marked, outside, smudged = make_ballot(positions, rule, rng)
        image = draw_ballot(
            positions, marked, skew_degrees=rng.uniform(-1.2, 1.2), noise=rng.random() < 0.4,
            seed=rng.randint(0, 10**6), ballot_no=f"{n:04d}", outside=outside, smudged=smudged,
        )
        if kind == "pdf":
            path = save_pdf([image], OUT / "pdfs" / f"Ballot_{n:04d}.pdf")
            note = "PDF 200 DPI"
        else:
            dpi, rotation, note = IMAGE_VARIANTS[index - 1]
            if dpi != DRAW_DPI:
                image = image.resize((round(image.width * dpi / DRAW_DPI), round(image.height * dpi / DRAW_DPI)), Image.LANCZOS)
            if rotation:
                image = image.rotate(rotation, expand=True, fillcolor="white")
            path = OUT / "images" / f"Ballot_{n:04d}.jpg"
            image.save(path, "JPEG", quality=85, dpi=(dpi, dpi))

        for p in positions:
            chosen = [c for c in p["candidates"] if c["voter_no"] in marked | outside | smudged]
            usable = [c for c in chosen if c["voter_no"] in marked]
            over = len(usable) > p["max_selections"]
            for c in chosen:
                if c["voter_no"] in outside:
                    result = "VOID - rule (kha): X outside the box"
                elif c["voter_no"] in smudged:
                    result = "VOID - rule (ga): box scribbled over"
                elif over:
                    result = "VOID - rule (ka): more marks than allowed"
                else:
                    result = "counted"
                    tally[kind][c["voter_no"]] += 1
                key_rows.append({
                    "ballot_no": f"{n:04d}", "file": f"{kind}s/{path.name}", "scan": note,
                    "post_no": p["post_no"], "post": p["name"], "voter_no": c["voter_no"],
                    "candidate": c["name"], "result": result,
                })
            if not chosen:
                key_rows.append({
                    "ballot_no": f"{n:04d}", "file": f"{kind}s/{path.name}", "scan": note,
                    "post_no": p["post_no"], "post": p["name"], "voter_no": "-",
                    "candidate": "(no vote)", "result": "-",
                })

    with (OUT / "answer_key.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0].keys()))
        w.writeheader()
        w.writerows(key_rows)
    with (OUT / "expected_tally.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["voter_no", "post_no", "post", "name_en", "name_bn", "votes_pdfs", "votes_images", "votes_total"])
        for p in positions:
            for c in p["candidates"]:
                a, b = tally["pdf"][c["voter_no"]], tally["image"][c["voter_no"]]
                w.writerow([c["voter_no"], p["post_no"], p["name"], c["name"], c["name_bn"], a, b, a + b])
    with (OUT / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["voter_no", "post_no", "post_en", "post_bn", "name_en", "name_bn"])
        for p in positions:
            for c in p["candidates"]:
                w.writerow([c["voter_no"], p["post_no"], p["name"], p["name_bn"], c["name"], c["name_bn"]])

    print(f"Wrote {PER_SET} PDFs, {PER_SET} images, candidates.csv, answer_key.csv and expected_tally.csv to {OUT}")


if __name__ == "__main__":
    main()
