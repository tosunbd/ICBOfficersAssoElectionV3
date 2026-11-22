r"""Generate anonymous candidate names and 15 sample ballots for resources/esource.

Run from the icbOfficerAssoAPI folder (uses the project's ballot drawer):

    .venv\Scripts\python "..\resources\esource\generate_samples.py"

Outputs (in resources/esource):
    candidates.csv / candidates.json   30 candidates (voter no 101-130), posts as on resources/ballot.jpg
    ballot_01.pdf ... ballot_15.pdf    filled sample ballots (valid, random choices, fixed seed)
    ballots_answer_key.csv             which candidate(s) each ballot marked
    expected_tally.csv                 vote count per candidate across the 15 ballots
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2] / "icbOfficerAssoAPI"
sys.path.insert(0, str(API_DIR))

from app.routers.elections import DEFAULT_POSITIONS  # noqa: E402
from app.utils.sample_ballot import draw_ballot, random_choices, save_pdf  # noqa: E402

OUT = Path(__file__).resolve().parent
SEED = 2026
BALLOTS = 15

# (name_en, name_bn) in ballot order: 2 per post, 6 for Executive Member -> voter no 101..130
CANDIDATES = [
    ("Md. Rafiqul Islam", "মোঃ রফিকুল ইসলাম"), ("Kazi Nurul Amin", "কাজী নুরুল আমিন"),
    ("Shamsul Haque Chowdhury", "শামসুল হক চৌধুরী"), ("Mahbubur Rahman Khan", "মাহবুবুর রহমান খান"),
    ("Abdul Hannan Sarker", "আব্দুল হান্নান সরকার"), ("Sultana Razia", "সুলতানা রাজিয়া"),
    ("Tanvir Ahmed Bhuiyan", "তানভীর আহমেদ ভূঁইয়া"), ("Farhana Yasmin", "ফারহানা ইয়াসমিন"),
    ("Md. Jahangir Alam", "মোঃ জাহাঙ্গীর আলম"), ("Nasrin Sultana", "নাসরিন সুলতানা"),
    ("Shahidul Islam Mridha", "শহিদুল ইসলাম মৃধা"), ("Golam Mostafa Talukder", "গোলাম মোস্তফা তালুকদার"),
    ("Zakir Hossain Patwary", "জাকির হোসেন পাটোয়ারী"), ("Rezaul Karim Sikder", "রেজাউল করিম সিকদার"),
    ("Shirin Akter", "শিরিন আক্তার"), ("Anisur Rahman Mondal", "আনিসুর রহমান মণ্ডল"),
    ("Sanjida Parvin", "সানজিদা পারভীন"), ("Ashraful Alam Sohel", "আশরাফুল আলম সোহেল"),
    ("Tapan Kumar Biswas", "তপন কুমার বিশ্বাস"), ("Rumana Afroz", "রুমানা আফরোজ"),
    ("Kamrul Hasan Bepari", "কামরুল হাসান বেপারী"), ("Subrata Kumar Saha", "সুব্রত কুমার সাহা"),
    ("Dilruba Akhter", "দিলরুবা আখতার"), ("Mizanur Rahman Howlader", "মিজানুর রহমান হাওলাদার"),
    ("Habibur Rahman Sheikh", "হাবিবুর রহমান শেখ"), ("Nazmul Huda Prodhan", "নাজমুল হুদা প্রধান"),
    ("Jesmin Ara Begum", "জেসমিন আরা বেগম"), ("Iqbal Mahmud Chowdhury", "ইকবাল মাহমুদ চৌধুরী"),
    ("Pranab Kumar Roy", "প্রণব কুমার রায়"), ("Md. Shafiqul Alam Munshi", "মোঃ শফিকুল আলম মুন্সী"),
]


def build_positions() -> list[dict]:
    positions, voter_no, idx = [], 101, 0
    for pos in DEFAULT_POSITIONS:
        cands = []
        for _ in range(6 if pos["position_order"] == 13 else 2):
            name_en, name_bn = CANDIDATES[idx]
            cands.append({"voter_no": str(voter_no), "name": name_en, "name_bn": name_bn})
            voter_no += 1
            idx += 1
        positions.append({
            "position_order": pos["position_order"], "name": pos["name_en"], "name_bn": pos["name_bn"],
            "max_selections": pos["max_selections"], "candidates": cands,
        })
    return positions


def main() -> None:
    positions = build_positions()

    rows = [{
        "voter_no": c["voter_no"], "post_no": p["position_order"], "post_en": p["name"], "post_bn": p["name_bn"],
        "name_en": c["name"], "name_bn": c["name_bn"],
    } for p in positions for c in p["candidates"]]
    with (OUT / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    (OUT / "candidates.json").write_text(json.dumps(positions, ensure_ascii=False, indent=2), encoding="utf-8")

    by_no = {c["voter_no"]: (p, c) for p in positions for c in p["candidates"]}
    rng = random.Random(SEED)
    tally: Counter[str] = Counter()
    key_rows = []
    for old in OUT.glob("ballot_*.pdf"):
        old.unlink()
    for n in range(1, BALLOTS + 1):
        marked = random_choices(positions, rng)
        tally.update(marked)
        image = draw_ballot(positions, marked, skew_degrees=rng.uniform(-1.0, 1.0),
                            noise=rng.random() < 0.3, seed=rng.randint(0, 10**6), ballot_no=f"{n:04d}")
        save_pdf([image], OUT / f"ballot_{n:02d}.pdf")
        for p in positions:
            chosen = [c for c in p["candidates"] if c["voter_no"] in marked]
            key_rows.append({
                "ballot": f"{n:02d}", "post_no": p["position_order"], "post_en": p["name"],
                "voter_no": ";".join(c["voter_no"] for c in chosen) or "-",
                "candidate": ";".join(c["name"] for c in chosen) or "(no vote)",
            })
    with (OUT / "ballots_answer_key.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=key_rows[0].keys())
        w.writeheader()
        w.writerows(key_rows)
    with (OUT / "expected_tally.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["voter_no", "post_no", "post_en", "name_en", "name_bn", "votes"])
        for no, (p, c) in by_no.items():
            w.writerow([no, p["position_order"], p["name"], c["name"], c["name_bn"], tally.get(no, 0)])
    print(f"Wrote {len(rows)} candidates, {BALLOTS} ballots and answer key to {OUT}")


if __name__ == "__main__":
    main()
