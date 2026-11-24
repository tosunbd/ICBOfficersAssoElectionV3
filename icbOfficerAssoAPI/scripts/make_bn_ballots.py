r"""Create the Bengali test ballots from the Word form of 24-11-2026 (QR code, bar code
at the bottom centre, 38 x 14 mm number box for the 6 digit numbering machine).

Run from the icbOfficerAssoAPI folder (needs Microsoft Word):

    .venv\Scripts\python scripts\make_bn_ballots.py [output folder]

Default output: <project>/Sample Ballots/24-11-2026
Form:       <that folder>/Blank ballot/Blank_ballot_form.docx   (read only)
Candidates: <that folder>/candidates.csv   (same names and left/right order as the form, read only)
    img_0001.jpg ... IMG_0025.JPEG        25 scanned ballots, every common voter mistake
                                          (img / extension in mixed case, as scanners name them)
    answer_key.csv                        every mark on every ballot and what the system must do with it
    expected_tally.csv                    correct totals
    README.txt                            what each ballot tests
    Blank ballot/Blank_ballot_form.pdf / .png   the unmarked form (no X anywhere)

The printed form is the Word document itself, exported by Word with an empty
number box (scripts/make_ballot_papers.py).  The ballot paper number is then
stamped into the box the way a hand-held numbering machine does it (6 Bengali
digits, ০০০০০১ ..., never quite straight or centred), the voter's pen marks are drawn on the page
with Pillow, and the page is "scanned" (DPI, skew, rotation, noise).  Fixed
seed: running the script again gives the same files.
"""

from __future__ import annotations

import csv
import random
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from app.routers.elections import DEFAULT_POSITIONS  # noqa: E402
from app.utils.paper_number import file_paper_no, find_number_box  # noqa: E402
from make_ballot_form import BALLOT_CODE  # noqa: E402
from make_ballot_papers import TEMPLATE, ballot_pdf, render_pages, template_candidates, write_blank  # noqa: E402

ROOT = API_DIR.parent
OUT = ROOT / "Sample Ballots" / "24-11-2026"
# the candidate list of the final ballot: read only, never written by this script
CANDIDATES_CSV = OUT / "candidates.csv"
SEED = 20261103

# ---------------------------------------------------------------- geometry
# A4 at 200 DPI.  প্রার্থী | বক্স | পদের নাম | প্রার্থী | বক্স : the post name sits in the
# middle column, between the post's two candidates; the Executive Member post
# (6 candidates, 3 rows) has one merged middle cell.  Both halves are identical.
PAGE_W, PAGE_H = 1654, 2339
TABLE_TOP = 191                # top line of the table
ROW_H = 107.6                  # header row and every candidate row
BOX_H = 76                     # vote box height
NAME_X = (120, 998)            # left edge of the candidate cell (left / right candidate)


# --------------------------------------------------------------- candidates
def load_positions() -> list[dict]:
    with CANDIDATES_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    positions = []
    for pos in DEFAULT_POSITIONS:
        cands = [
            {"voter_no": r["voter_no"].strip(), "name": r["name_en"].strip(), "name_bn": r["name_bn"].strip()}
            for r in rows if int(r["post_no"]) == pos["position_order"]
        ]
        positions.append({
            "post_no": pos["position_order"], "name": pos["name_en"], "name_bn": pos["name_bn"],
            "max_selections": pos["max_selections"], "candidates": cands,
        })
    return positions


def find_boxes(form: Image.Image) -> list[tuple[int, int, int, int]]:
    """Vote boxes printed on the form (thin blue rectangles inside the table) as
    (x0, y0, x1, y1), row by row, the left box before the right one."""
    rgb = np.asarray(form).astype(int)
    blue = ((rgb[:, :, 2] - rgb[:, :, 0]) > 60).astype(np.uint8) * 255
    contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = [cv2.boundingRect(c) for c in contours]
    rects = [(x, y, x + w, y + h) for x, y, w, h in rects if w > 80 and h > 50 and y > TABLE_TOP]
    return sorted(rects, key=lambda r: (round((r[1] - TABLE_TOP) / ROW_H), r[0]))


def layout(positions: list[dict], form: Image.Image) -> tuple[dict[str, tuple[int, int, int, int]], dict[str, tuple[int, int, int, int]]]:
    """(box_by_voter, name_by_voter) measured on the printed form.

    Each table row holds two candidates of one post, in CSV order (first = left);
    a post with more (Executive Member) takes several rows.
    """
    cands = [c for pos in positions for c in pos["candidates"]]
    printed = template_candidates(TEMPLATE)
    listed = [(c["voter_no"], c["name_bn"]) for c in cands]
    if printed != listed:
        diff = [f"{a} / {b}" for a, b in zip(printed, listed) if a != b][:3]
        raise SystemExit(f"{CANDIDATES_CSV.name} does not match the names or their order on {TEMPLATE.name}: {diff}")
    rects = find_boxes(form)
    if len(rects) != len(cands):
        raise SystemExit(f"{len(rects)} vote boxes found on the form for {len(cands)} candidates")
    boxes, names = {}, {}
    for (x0, y0, x1, y1), cand in zip(rects, cands):
        boxes[cand["voter_no"]] = (x0, y0, x1, y1)
        side = 0 if x0 < PAGE_W / 2 else 1
        # the name line (second line of the candidate cell), clear of the box cell
        names[cand["voter_no"]] = (NAME_X[side] + 10, y0 + 37, x0 - 37, y0 + 80)
    return boxes, names


# ------------------------------------------------------- numbering machine
STAMP_DIGITS = 6               # wheels of the numbering machine: paper 1 is stamped ০০০০০১
LAST_PAPER = 455               # papers ০০০০০১ ... ০০০৪৫৫ are issued
STAMP_FONTS = ("kalpurush.ttf", "Siyamrupali.ttf", "Nirmala.ttc")   # Bengali digit wheels
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
STAMP_INK = (28, 28, 34)
FONTS_DIR = Path("C:/Windows/Fonts")


def stamped(paper: str) -> str:
    """The number as the system reads and stores it: 6 digits (000001)."""
    return f"{int(paper):0{STAMP_DIGITS}d}"


def stamped_bn(paper: str) -> str:
    """The number as the machine stamps it on the paper: ০০০০০১."""
    return stamped(paper).translate(BN_DIGITS)


def stamp_number(page: Image.Image, paper: str, rng: random.Random) -> None:
    """Stamp the ballot paper number into the number box: digits about 5 mm high,
    a little off centre, slightly tilted and unevenly inked."""
    box = find_number_box(np.asarray(page.convert("L")))
    if box is None:
        raise SystemExit("The ballot paper number box was not found on the form")
    x, y, w, h = box
    font_file = next((FONTS_DIR / name for name in STAMP_FONTS if (FONTS_DIR / name).exists()), None)
    if font_file is None:
        raise SystemExit(f"None of the fonts {STAMP_FONTS} is installed")
    font = ImageFont.truetype(str(font_file), 54)
    text = stamped_bn(paper)
    layer = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(layer)
    advance = max(draw.textlength(d, font=font) for d in "০১২৩৪৫৬৭৮৯") + 6
    left = (w - advance * len(text)) / 2
    for i, digit in enumerate(text):
        draw.text((left + i * advance + advance / 2, h / 2), digit, fill=255, font=font, anchor="mm")
    ink = np.asarray(layer, dtype=np.float32) * np.random.default_rng(int(paper)).uniform(0.72, 1.0, (h, w))
    layer = Image.fromarray(ink.astype(np.uint8)).rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC)
    page.paste(Image.new("RGB", (w, h), STAMP_INK), (x + rng.randint(-30, 30), y + rng.randint(-12, 12)), layer)


# ---------------------------------------------------------------- pen marks
INK = (25, 30, 60)  # ball-point blue-black


def _stroke(draw, pts, width, fill=INK):
    draw.line(pts, fill=fill, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def pen_x(draw, box, rng, fill=INK, width=None, pad=10):
    x0, y0, x1, y1 = box
    j = lambda: rng.randint(-4, 4)  # noqa: E731
    w = width or rng.randint(5, 7)
    _stroke(draw, [(x0 + pad + j(), y0 + pad + j()), (x1 - pad + j(), y1 - pad + j())], w, fill)
    _stroke(draw, [(x1 - pad + j(), y0 + pad + j()), (x0 + pad + j(), y1 - pad + j())], w, fill)


def pen_x_across(draw, box, rng):
    """X far bigger than the box: the strokes cross the border (rule kha)."""
    x0, y0, x1, y1 = box
    o = 30
    _stroke(draw, [(x0 - o, y0 - o // 2), (x1 + o, y1 + o // 2)], 6)
    _stroke(draw, [(x1 + o, y0 - o // 2), (x0 - o, y1 + o // 2)], 6)


def pen_x_beside(draw, box, rng):
    """X drawn just to the left of the box, the box itself left clean."""
    x0, y0, x1, y1 = box
    w = 64
    bx1 = x0 - 4
    pen_x(draw, (bx1 - w, y0 + 4, bx1, y1 - 4), rng, pad=4)


def scribble(draw, box, rng):
    """Box rubbed / scribbled over (rule ga)."""
    x0, y0, x1, y1 = box
    y = y0 + 5
    while y < y1 - 4:
        _stroke(draw, [(x0 + 5, y), (x1 - 5, y + rng.randint(2, 6))], 7)
        y += 5
    for _ in range(6):
        _stroke(draw, [(x0 + rng.randint(5, 30), y0 + rng.randint(5, BOX_H - 6)), (x1 - rng.randint(5, 30), y0 + rng.randint(5, BOX_H - 6))], 6)


def tick(draw, box, rng):
    x0, y0, x1, y1 = box
    _stroke(draw, [(x0 + 22, y0 + 40), (x0 + 50, y1 - 12), (x1 - 16, y0 + 10)], 6)


def slash(draw, box, rng):
    x0, y0, x1, y1 = box
    _stroke(draw, [(x0 + 18, y1 - 12), (x1 - 18, y0 + 12)], 6)


def dot(draw, box, rng):
    x0, y0, x1, y1 = box
    cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, 5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK)


def pencil_x(draw, box, rng):
    pen_x(draw, box, rng, fill=(135, 135, 140), width=3)


def x_on_name(draw, name_area, rng):
    x0, y0, x1, y1 = name_area
    pen_x(draw, (x0 + 40, y0 - 12, x0 + 180, y1 + 2), rng, pad=0)


def circle_name(draw, name_area, rng):
    x0, y0, x1, y1 = name_area
    draw.ellipse([x0 - 6, y0 - 8, x1 - 20, y1 + 6], outline=INK, width=4)


MARKS = {
    "x": pen_x, "across": pen_x_across, "beside": pen_x_beside, "scribble": scribble,
    "tick": tick, "slash": slash, "dot": dot, "pencil": pencil_x,
}
NAME_MARKS = {"x_name": x_on_name, "circle_name": circle_name}

# what the counting system must do with each kind of mark
RESULT = {
    "x": "counted", "tick": "counted", "slash": "counted", "pencil": "counted",
    "across": "VOID - rule (kha): X crosses the box border",
    "beside": "VOID - rule (kha): mark outside the box",
    "scribble": "VOID - rule (ga): box scribbled over",
    "dot": "counted - unclear mark and the other box of the post is empty",
    "x_name": "not a vote - X on the name, box empty",
    "circle_name": "not a vote - name circled, box empty",
}
VOID_KINDS = {"across", "beside", "scribble"}
NO_VOTE_KINDS = {"x_name", "circle_name"}       # the box itself is not touched
COUNTED_KINDS = {"x", "tick", "slash", "pencil", "dot"}


# ------------------------------------------------------------ ballot plans
def random_votes(positions: list[dict], rng: random.Random, abstain: float = 0.0) -> dict[str, str]:
    """A normal voter: one X per post, up to the limit for Executive Member."""
    marks: dict[str, str] = {}
    for p in positions:
        if rng.random() < abstain:
            continue
        k = p["max_selections"] if p["max_selections"] == 1 else rng.randint(1, p["max_selections"])
        for c in rng.sample(p["candidates"], k):
            marks[c["voter_no"]] = "x"
    return marks


def post_cands(positions, post_no) -> list[str]:
    return [c["voter_no"] for c in positions[post_no - 1]["candidates"]]


def plans(positions: list[dict], rng: random.Random) -> list[dict]:
    """25 ballots.  Each: no, paper (printed number), note, marks {voter_no: kind}, scan."""
    P = lambda n: post_cands(positions, n)  # noqa: E731
    out: list[dict] = []

    def ballot(note, marks=None, *, abstain=0.0, scan=None, paper=None, base=None):
        m = random_votes(positions, rng, abstain) if base is None else dict(base)
        for voter, kind in (marks or {}).items():
            if kind is None:
                m.pop(voter, None)
            else:
                m[voter] = kind
        n = len(out) + 1
        out.append({"no": n, "paper": paper or f"{n:04d}", "note": note, "marks": m,
                    "scan": scan or {"dpi": 200, "skew": rng.uniform(-0.6, 0.6)}})
        return m

    def clear(*posts):
        return {v: None for p in posts for v in P(p)}

    ballot("Correct ballot: one X in every post, 3 Executive Members")
    ballot("Correct ballot (this paper is photocopied as file no 0021)")
    ballot("Some posts left blank on purpose (allowed)", abstain=0.35)
    ballot("Rule (ka): two X for President -> both President marks void",
           {**clear(1), P(1)[0]: "x", P(1)[1]: "x"})
    ballot("Rule (kha): Vice President X crosses the box border -> void",
           {**clear(2), P(2)[1]: "across"})
    ballot("Rule (ga): General Secretary box scribbled over -> void",
           {**clear(3), P(3)[0]: "scribble"})
    ballot("Treasurer box 1 scribbled out, X in box 2 -> both boxes touched, no vote for the post",
           {**clear(5), P(5)[0]: "scribble", P(5)[1]: "x"})
    ballot("Tick marks instead of X (President, Office Secretary, Sports Secretary) -> counted",
           {**clear(1, 7, 11), P(1)[1]: "tick", P(7)[0]: "tick", P(11)[1]: "tick"})
    ballot("Single slash '/' instead of X (Asst. Gen. Secretary, Drama Secretary) -> counted",
           {**clear(4, 10), P(4)[0]: "slash", P(10)[1]: "slash"})
    ballot("Only a small dot in the Cultural Secretary box, the other box empty -> the dot counts",
           {**clear(9), P(9)[0]: "dot"})
    ballot("Rule (ka): 4 Executive Members marked (3 allowed) -> all 4 void",
           {**clear(13), **{v: "x" for v in P(13)[:4]}})
    ballot("Only 1 Executive Member marked (fewer than 3 is allowed) -> counted",
           {**clear(13), P(13)[2]: "x"})
    ballot("Rule (kha): Publication Secretary X drawn beside the box, box empty -> void",
           {**clear(8), P(8)[1]: "beside"})
    ballot("X on the candidate's NAME (Organizing Secretary) and a circled name (Hospitality) -> no vote",
           {**clear(6, 12), P(6)[0]: "x_name", P(12)[1]: "circle_name"})
    ballot("Faint pencil X marks everywhere -> counted",
           base={v: "pencil" for v in random_votes(positions, rng)})
    ballot("Stray pen line across the names (not through a box) -> ignored; votes counted")
    out[-1]["stray"] = True
    ballot("Completely blank ballot -> 0 votes", base={})
    ballot("Every box marked -> every post over-voted, all void (rule ka)",
           base={c["voter_no"]: "x" for p in positions for c in p["candidates"]})
    ballot("Scanned crooked (2.5 degrees) at 150 DPI; scanner operator typed the file number wrong (0091) -> mismatch",
           scan={"dpi": 150, "skew": 2.5})
    out[-1]["file_no"] = "0091"
    ballot("Scanned upside down -> turned upright, counted", scan={"dpi": 200, "skew": 0.3, "rotate": 180})
    # 21: photocopy of paper 0002 (same marks, same number)
    out.append({**out[1], "no": 21, "note": "PHOTOCOPY of paper 0002 saved as file 0021 -> the file number 0021 does not match paper 0002",
                "scan": {"dpi": 200, "skew": -0.9, "photocopy": True}})
    ballot("Paper 0026 saved as file 0022 -> the file number does not match the printed number", paper="0026")
    ballot("Ballot paper number box left empty -> the paper number cannot be read, needs review")
    out[-1]["blank_no"] = True
    ballot("Scanned sideways at 300 DPI -> turned upright, counted", scan={"dpi": 300, "skew": 0.0, "rotate": 90})
    ballot("Mixed: two X Treasurer (ka), X across border Sports (kha), tick Drama, dark noisy scan",
           {**clear(5, 11, 10), P(5)[0]: "x", P(5)[1]: "x", P(11)[0]: "across", P(10)[0]: "tick"},
           scan={"dpi": 200, "skew": -1.2, "noise": True})
    assert len(out) == 25
    return out


# scanners name files IMG_0001.JPG, img_0001.jpeg ...: every spelling must be accepted
NAME_CASES = ["img", "IMG", "Img", "iMg", "imG", "IMg", "iMG", "ImG"]
EXT_CASES = ["jpg", "jpeg", "JPG", "JPEG", "Jpg", "jPeg"]


def file_name(plan: dict) -> str:
    """img_<number>.jpg in mixed case; the number is the paper number unless the plan
    sets a wrong one on purpose (file_no)."""
    n = plan["no"]
    return f"{NAME_CASES[n % len(NAME_CASES)]}_{plan.get('file_no', f'{n:04d}')}.{EXT_CASES[n % len(EXT_CASES)]}"


# --------------------------------------------------------------- scanning
def draw_marks(page: Image.Image, plan: dict, boxes, names, rng: random.Random) -> Image.Image:
    draw = ImageDraw.Draw(page)
    for voter, kind in plan["marks"].items():
        if kind in NAME_MARKS:
            NAME_MARKS[kind](draw, names[voter], rng)
        else:
            MARKS[kind](draw, boxes[voter], rng)
    if plan.get("stray"):
        # a slip of the pen through the name columns, well clear of the boxes
        _stroke(draw, [(200, 420), (400, 900), (300, 1300)], 4)
        _stroke(draw, [(1120, 1640), (1330, 1880)], 4)
    return page


def scan(page: Image.Image, plan: dict, rng: random.Random) -> tuple[Image.Image, int]:
    s = plan["scan"]
    img = page
    if s.get("photocopy"):
        arr = np.asarray(img.convert("L"), dtype=np.float32)
        arr = np.clip((arr - 30) * 1.15, 0, 255)  # darker, more contrast, grey toner
        arr += np.random.default_rng(plan["no"]).normal(0, 9, arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)).convert("RGB")
    if s.get("skew"):
        img = img.rotate(s["skew"], resample=Image.BICUBIC, expand=False, fillcolor="white")
    if s.get("noise"):
        arr = np.asarray(img, dtype=np.int16)
        arr = arr - 28 + np.random.default_rng(plan["no"]).integers(-22, 22, arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    dpi = s.get("dpi", 200)
    if dpi != 200:
        img = img.resize((round(img.width * dpi / 200), round(img.height * dpi / 200)), Image.LANCZOS)
    if s.get("rotate"):
        img = img.rotate(s["rotate"], expand=True, fillcolor="white")
    return img, dpi


def scan_note(plan: dict) -> str:
    s = plan["scan"]
    bits = [f"{s.get('dpi', 200)} DPI"]
    if abs(s.get("skew", 0)) >= 1:
        bits.append(f"skewed {s['skew']:+.1f} deg")
    if s.get("rotate") == 180:
        bits.append("upside down")
    elif s.get("rotate"):
        bits.append("sideways")
    if s.get("photocopy"):
        bits.append("photocopy")
    if s.get("noise"):
        bits.append("dark noisy scan")
    return ", ".join(bits)


# ------------------------------------------------------------------- main
def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    # only the scans this script writes (img_<number>.jpg / .jpeg): never other files in
    # the folder, such as the approved ballot PDF (Windows globs ignore case)
    for old in [p for p in out_dir.iterdir() if p.is_file() and file_paper_no(p.name)]:
        old.unlink()
    positions = load_positions()
    rng = random.Random(SEED)
    all_plans = plans(positions, rng)

    key_rows: list[dict] = []
    tally = Counter()
    work = Path(tempfile.mkdtemp(prefix="icb-ballots-"))
    try:
        # the Word form (empty number box), exported by Word; the numbers are stamped on it
        ballot_pdf([None], work / "forms.pdf")
        form = render_pages(work / "forms.pdf")[0]
        boxes, names = layout(positions, form)
        for plan in all_plans:
            paper = plan["paper"]
            printed = None if plan.get("blank_no") else stamped(paper)
            page = form.copy()
            if printed:
                stamp_number(page, paper, random.Random(SEED - int(paper)))
            page = draw_marks(page, plan, boxes, names, random.Random(SEED + int(paper)))
            img, dpi = scan(page, plan, rng)
            path = out_dir / file_name(plan)
            img.save(path, "JPEG", quality=88, dpi=(dpi, dpi))
            print(f"  {path.name}  {plan['note']}")

            for p in positions:
                chosen = [c for c in p["candidates"] if c["voter_no"] in plan["marks"]]
                # rule (ka): every box the voter touched counts towards the limit - a clear
                # mark, an unclear one (dot) and one that is void by rules (kha)/(ga)
                touched = [c for c in chosen if plan["marks"][c["voter_no"]] not in NO_VOTE_KINDS]
                usable = [c for c in touched if plan["marks"][c["voter_no"]] in COUNTED_KINDS]
                over = len(touched) > p["max_selections"]
                for c in chosen:
                    kind = plan["marks"][c["voter_no"]]
                    result = RESULT[kind]
                    if kind in COUNTED_KINDS and over:
                        result = ("VOID - rule (ka): more marks than allowed for the post" if len(usable) > p["max_selections"]
                                  else "VOID - rule (ka): both boxes of the post are touched")
                    if result.startswith("counted"):
                        tally[c["voter_no"]] += 1
                    key_rows.append({
                        "file": path.name, "paper_no": printed or "(blank)",
                        "scan": scan_note(plan), "post_no": p["post_no"], "post": p["name"],
                        "voter_no": c["voter_no"], "candidate": c["name"], "mark": kind, "result": result,
                    })
                if not chosen:
                    key_rows.append({
                        "file": path.name, "paper_no": printed or "(blank)",
                        "scan": scan_note(plan), "post_no": p["post_no"], "post": p["name"],
                        "voter_no": "-", "candidate": "(no vote)", "mark": "-", "result": "-",
                    })
        # the unmarked form (no X anywhere, empty number box) to print or show the voters
        blank_dir = out_dir / "Blank ballot"
        blank_dir.mkdir(exist_ok=True)
        write_blank(blank_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with (out_dir / "answer_key.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0].keys()))
        w.writeheader()
        w.writerows(key_rows)
    with (out_dir / "expected_tally.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["voter_no", "post_no", "post", "name_en", "name_bn", "votes_counted_by_system"])
        for p in positions:
            for c in p["candidates"]:
                w.writerow([c["voter_no"], p["post_no"], p["name"], c["name"], c["name_bn"],
                            tally[c["voter_no"]]])
    if (out_dir / "candidates.csv").resolve() != CANDIDATES_CSV.resolve():
        shutil.copyfile(CANDIDATES_CSV, out_dir / "candidates.csv")
    (out_dir / "README.txt").write_text(readme(all_plans, sum(tally.values()), out_dir.name), encoding="utf-8")
    print(f"Wrote 25 ballots to {out_dir}")


def review_reason(plan: dict, positions: list[dict]) -> str:
    kinds = set(plan["marks"].values())
    reasons = []
    file_no = plan.get("file_no", f"{plan['no']:04d}")
    if plan.get("blank_no"):
        reasons.append(f"file number {file_no}: paper number cannot be read")
    elif file_no != plan["paper"]:
        reasons.append(f"file number {file_no} does not match paper {stamped(plan['paper'])}")
    if kinds & VOID_KINDS:
        reasons.append("void mark")
    for p in positions:
        usable = [c for c in p["candidates"] if plan["marks"].get(c["voter_no"]) in COUNTED_KINDS]
        if len(usable) > p["max_selections"]:
            reasons.append("over-vote")
            break
    status = "Needs review: " + ", ".join(reasons) if reasons else "Processed"
    if kinds & {"tick", "slash"}:
        status += " (a tick / slash counts; a light one lowers the confidence and may also ask for review)"
    return status


def readme(all_plans: list[dict], total: int, folder: str) -> str:
    positions = load_positions()
    lines = [
        f"SAMPLE BALLOTS {folder} - Bengali ballot with QR code, bar code and large number box",
        "(Blank ballot\\Blank_ballot_form.docx)",
        "=" * 84,
        "",
        "25 scanned ballot images (JPG), A4, made from the Word form itself (exported by Word):",
        "QR code and Bengali title, ballot paper number box (38 x 14 mm), then one row",
        "per post with the post name in the middle column and its two candidates on either side:",
        "  voter no + candidate name | box | post name | voter no + candidate name | box",
        "Executive Member (6 candidates, up to 3 votes) takes 3 rows with one merged post-name cell.",
        "Footer: the instructions (ka/kha/ga), Election Commissioner and seal; bar code bottom centre.",
        "Same form as 17-11-2026 (same names, same table, same place on the page) plus:",
        f"  - QR code (top left) and bar code (bottom centre, under the candidate table; it was at the",
        f"    bottom left on the form of 19-11-2026), both reading {BALLOT_CODE} on every paper;",
        "    the counting system does not need them, they mark the paper as a ballot of this election.",
        "  - a larger number box (38 x 14 mm; it was 32 x 12 mm on the form of 21-11-2026): the form is",
        f"    printed WITHOUT a number and the {STAMP_DIGITS} digit ballot paper number ({stamped_bn('1')} ... {stamped_bn(str(LAST_PAPER))})",
        "    is stamped into the box by hand with the automatic numbering machine.",
        "Both halves are the same: equal candidate columns, equal boxes, one font size.",
        "Candidates: candidates.csv of this folder = the names and the left / right places of the",
        "Word form (first candidate of a row = left side). Voter number on the first line, name below.",
        "",
        "FILE NAME MUST MATCH THE BALLOT NUMBER",
        "  Images named img_<number>.jpg are checked: the number in the file name must be the ballot",
        "  paper number stamped in the box at the top right (read from the scan). 'img' and the",
        "  extension may be any upper/lower case (IMG_0001.JPG, iMg_0001.Jpeg); jpg and jpeg are both",
        "  accepted. Leading zeros do not count: img_0001 = paper 000001 = paper 1.",
        "  A mismatch, or a paper whose number cannot be read, goes to 'Needs review'.",
        f"  So does a number that was never issued (above {stamped(str(LAST_PAPER))} = Total voters of the election).",
        "  Bengali (০-৯) and English (0-9) digits are both read; the system shows them as 000001.",
        "  Stamp the number INSIDE the box, clear of its border, in dark ink (black or blue).",
        "  Here: 0019 is saved as ..._0091 (typing error), 0021 is a photocopy of paper 0002, 0022 is",
        "  paper 0026, and 0023 has an empty number box.",
        "",
        "FILES",
        "  img_0001.jpg ... IMG_0025.JPEG  (mixed case on purpose)",
        "  candidates.csv      the 30 candidates  <-- IMPORT THIS FIRST (Admin -> Candidates -> Import CSV)",
        "  answer_key.csv      every mark on every ballot and what the system must do with it",
        "  expected_tally.csv  votes_counted_by_system = what Admin -> Results must show",
        f"  Total valid votes: {total}.",
        "  Blank ballot\\Blank_ballot_form.docx          the form (Word) - the source of everything here",
        "  Blank ballot\\Blank_ballot_form.png / .pdf   the unmarked form (no X, no number) - PRINT THIS",
        f"                      ({LAST_PAPER} copies), then stamp the numbers. Do NOT copy it into the Scanned folder.",
        "",
        "WHAT EACH BALLOT TESTS                                                         expected status",
        "-" * 110,
    ]
    for plan in all_plans:
        printed = "------" if plan.get("blank_no") else stamped(plan["paper"])
        lines.append(f"  {file_name(plan):<16}  paper {printed}  {plan['note']}")
        lines.append(f"        scan: {scan_note(plan)};  -> {review_reason(plan, positions)}")
    lines += [
        "",
        "TEST PROCEDURE",
        "1. Start the system, open Admin (admin / admin123).",
        "2. Elections: create the election, set it Active.",
        "3. Candidates: Import CSV -> this folder's candidates.csv (30 candidates, 13 posts).",
        "4. Copy all 25 image files into the Scanned folder (Admin -> Overview) and process them.",
        "5. Compare Admin -> Results with expected_tally.csv (votes_counted_by_system).",
        "   Ballots -> filter 'Needs review': open 0019, 0021, 0022 and 0023 - the warning list states",
        "   'File number: ...' (mismatch / number not readable).",
        "",
        "To rebuild this folder (same ballots, fixed seed):",
        "  cd icbOfficerAssoAPI",
        "  .venv\\Scripts\\python scripts\\make_bn_ballots.py        (needs Microsoft Word)",
        "The form itself (QR code, bar code, number box) is built by scripts\\make_ballot_form.py.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
