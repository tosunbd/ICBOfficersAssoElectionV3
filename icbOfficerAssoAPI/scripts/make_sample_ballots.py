"""Create sample scanned-ballot PDFs for testing the system without a scanner.

The candidates are read from the running election (via the API) so the
generated ballots always match the configured layout.

Usage (from the icbOfficerAssoAPI folder, with the API running):

    python scripts/make_sample_ballots.py --count 10 --out ../data/Scanned
    python scripts/make_sample_ballots.py --count 5 --overvote 1 --skew 1.5

Options:
    --api       API base URL (default http://localhost:8000)
    --election  election id (default: the active election)
    --count     how many ballots to create (default 5)
    --overvote  how many of them should contain an over-vote (default 0)
    --skew      rotate pages by up to this many degrees (default 1.0)
    --pages     pages per PDF, e.g. 10 to simulate a batch scanner (default 1)
    --out       output folder (default ../data/Scanned  -> processed automatically)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.sample_ballot import draw_ballot, random_choices, save_pdf  # noqa: E402


def fetch(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--election", type=int)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--overvote", type=int, default=0)
    parser.add_argument("--skew", type=float, default=1.0)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data" / "Scanned"))
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    election_id = args.election or fetch(f"{args.api}/api/dashboard/active")["id"]
    detail = fetch(f"{args.api}/api/elections/{election_id}")
    candidates = fetch(f"{args.api}/api/candidates/election/{election_id}")
    if not candidates:
        sys.exit("The election has no candidates yet – add them in the admin panel first.")

    positions = []
    for pos in sorted(detail["positions"], key=lambda p: p["position_order"]):
        cands = sorted((c for c in candidates if c["position_id"] == pos["id"]), key=lambda c: (c["display_order"], c["id"]))
        positions.append({
            "name": pos["name_en"], "max_selections": pos["max_selections"],
            "candidates": [{"voter_no": c["voter_no"], "name": c["name_en"]} for c in cands],
        })

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pages, files = [], 0
    for index in range(args.count):
        marked = random_choices(positions, rng)
        if index < args.overvote:  # add an extra mark in the first position
            extra = [c["voter_no"] for c in positions[0]["candidates"] if c["voter_no"] not in marked]
            if extra:
                marked.add(extra[0])
        skew = rng.uniform(-args.skew, args.skew) if args.skew else 0.0
        pages.append(draw_ballot(positions, marked, skew_degrees=skew, noise=rng.random() < 0.3, seed=rng.randint(0, 10**6)))
        if len(pages) == args.pages or index == args.count - 1:
            files += 1
            path = save_pdf(pages, out / f"sample_ballot_{rng.randint(1000, 9999)}_{index + 1:03d}.pdf")
            print("wrote", path)
            pages = []

    print(f"Created {files} PDF file(s) with {args.count} ballot page(s) in {out}")


if __name__ == "__main__":
    main()
