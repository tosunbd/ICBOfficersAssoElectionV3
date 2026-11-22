r"""Read a sample-ballot folder with the counting engine and compare with its answer_key.csv.

    .venv\Scripts\python scripts\check_sample_ballots.py ["..\Sample Ballots\21-11-2026"]

No database is used: the candidate layout comes from the folder's
candidates.csv, and the ballot rules (ka/kha/ga) are applied exactly like
`BallotProcessor._store_page` does.  Prints one line per ballot and exits
with status 1 if any mark differs from the answer key.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from app.routers.elections import DEFAULT_POSITIONS  # noqa: E402
from app.services.ocr_service import ocr_service  # noqa: E402
from app.utils.paper_number import file_paper_no, read_paper_no, same_paper  # noqa: E402

DEFAULT_DIR = API_DIR.parent / "Sample Ballots" / "21-11-2026"


def build_layout(folder: Path) -> tuple[list[dict], dict[int, int]]:
    with (folder / "candidates.csv").open(encoding="utf-8-sig", newline="") as f:
        # ballot order = the CSV order within each post, exactly as Import CSV stores it
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["post_no"]))
    max_by_post = {p["position_order"]: p["max_selections"] for p in DEFAULT_POSITIONS}
    layout, row_index, current, slot = [], -1, None, 0
    for r in rows:
        post = int(r["post_no"])
        if post != current:
            current, slot = post, 0
            row_index += 1
        elif slot == 2:
            row_index += 1
            slot = 0
        layout.append({"candidate_id": int(r["voter_no"]), "position_id": post, "row_index": row_index, "col_index": slot})
        slot += 1
    return layout, max_by_post


def read_ballot(path: Path, layout, max_by_post) -> tuple[dict[int, str], object, str | None]:
    page = ocr_service.process_file(path, layout)[0]
    by_post = defaultdict(list)
    for m in page.marks:
        if m.is_marked:
            by_post[m.position_id].append(m)
    result: dict[int, str] = {}
    for post, marks in by_post.items():
        # every touched box counts towards the limit (clear, unclear or void), as in _store_page
        over = len(marks) > max_by_post[post]
        for m in marks:
            if m.void_reason:
                result[m.candidate_id] = "VOID " + m.void_reason.split(":")[0].replace("Rule ", "")
            elif over:
                result[m.candidate_id] = "VOID (ka)"
            else:
                result[m.candidate_id] = "counted"
    return result, page, read_paper_no(page.image)


def expected(folder: Path) -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = defaultdict(dict)
    with (folder / "answer_key.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out[r["file"]]  # every file appears, even with no marks
            if r["voter_no"] == "-":
                continue
            res = r["result"]
            if res.startswith("counted"):
                out[r["file"]][int(r["voter_no"])] = "counted"
            elif res.startswith("VOID"):
                out[r["file"]][int(r["voter_no"])] = "VOID " + res.split("rule ")[1].split(")")[0] + ")"
    return out


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    layout, max_by_post = build_layout(folder)
    want = expected(folder)
    bad = 0
    files = [p for p in folder.iterdir() if file_paper_no(p.name)]
    for path in sorted(files, key=lambda p: p.name.lower()):
        got, page, printed = read_ballot(path, layout, max_by_post)
        exp = want.get(path.name, {})
        diff = {k: (exp.get(k, "-"), got.get(k, "-")) for k in set(exp) | set(got) if exp.get(k) != got.get(k)}
        file_no = file_paper_no(path.name)
        name_check = "name ok" if same_paper(file_no, printed) else f"NAME MISMATCH (file {file_no}, paper {printed or '?'})"
        flag = "OK " if not diff and page.layout_ok else "BAD"
        bad += bool(diff) or not page.layout_ok
        counted = sum(v == "counted" for v in got.values())
        void = sum(v.startswith("VOID") for v in got.values())
        low = min((m.confidence for m in page.marks if m.box is not None), default=1)
        print(f"{flag} {path.name}: boxes {page.boxes_detected}/{page.boxes_expected}, counted {counted}, void {void}, "
              f"min conf {low:.2f}, printed no {printed or '?'}, {name_check}")
        for k, (e, g) in sorted(diff.items()):
            print(f"      candidate {k}: expected {e}, read {g}")
        for w in page.warnings:
            if "turned" in w or "Expected" in w:
                print(f"      warning: {w}")
    print("ALL MATCH" if not bad else f"{bad} ballot(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
