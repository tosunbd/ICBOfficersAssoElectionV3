"""Prepare a complete rehearsal: election + anonymous candidates + sample ballots.

Writes directly to the database (the API does not need to be running) and
creates one PDF per ballot in the Scanned folder.  Then start the system, log
in, open Admin -> Ballots and press "Process Scanned folder now": the public
dashboard (http://localhost:3000/dashboard) updates after every ballot.

Usage (from the icbOfficerAssoAPI folder):

    .venv\\Scripts\\python scripts\\seed_rehearsal.py                 # 10 ballots
    .venv\\Scripts\\python scripts\\seed_rehearsal.py --count 25 --overvote 2 --violations
    .venv\\Scripts\\python scripts\\seed_rehearsal.py --ballots-only   # keep the election, new PDFs only

The election is called "Rehearsal Election"; running the script again deletes the
previous rehearsal election (and its ballots) and starts fresh.  Positions are the
13 posts printed on resources/ballot.jpg; candidate names are anonymous.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, init_db  # noqa: E402
from app.main import create_default_admin  # noqa: E402
from app.models import Candidate, Election, Position  # noqa: E402
from app.models.election import ElectionStatus  # noqa: E402
from app.routers.elections import DEFAULT_POSITIONS  # noqa: E402
from app.utils.sample_ballot import draw_ballot, random_choices, save_pdf  # noqa: E402

REHEARSAL_TITLE = "Rehearsal Election"
REHEARSAL_TITLE_BN = "আইসিবি কর্মকর্তা সমিতির ২০তম কার্যনির্বাহী পরিষদ নির্বাচন-২০২৬"

# 30 anonymous candidates, in ballot order (2 per post, 6 for Executive Member)
ANONYMOUS_NAMES = [
    ("Mr. Alpha", "জনাব আলফা"), ("Mr. Bravo", "জনাব ব্রাভো"),
    ("Mr. Charlie", "জনাব চার্লি"), ("Mr. Delta", "জনাব ডেল্টা"),
    ("Mr. Echo", "জনাব ইকো"), ("Mr. Foxtrot", "জনাব ফক্সট্রট"),
    ("Mr. Golf", "জনাব গলফ"), ("Mr. Hotel", "জনাব হোটেল"),
    ("Mr. India", "জনাব ইন্ডিয়া"), ("Mr. Juliet", "জনাব জুলিয়েট"),
    ("Mr. Kilo", "জনাব কিলো"), ("Mr. Lima", "জনাব লিমা"),
    ("Mr. Mike", "জনাব মাইক"), ("Mr. November", "জনাব নভেম্বর"),
    ("Mr. Oscar", "জনাব অস্কার"), ("Mr. Papa", "জনাব পাপা"),
    ("Mr. Quebec", "জনাব কুইবেক"), ("Mr. Romeo", "জনাব রোমিও"),
    ("Mr. Sierra", "জনাব সিয়েরা"), ("Mr. Tango", "জনাব ট্যাঙ্গো"),
    ("Mr. Uniform", "জনাব ইউনিফর্ম"), ("Mr. Victor", "জনাব ভিক্টর"),
    ("Mr. Whiskey", "জনাব হুইস্কি"), ("Mr. Xray", "জনাব এক্স-রে"),
    ("Mr. Yankee", "জনাব ইয়াঙ্কি"), ("Mr. Zulu", "জনাব জুলু"),
    ("Mr. Amber", "জনাব অ্যাম্বার"), ("Mr. Blue", "জনাব ব্লু"),
    ("Mr. Coral", "জনাব কোরাল"), ("Mr. Dune", "জনাব ডিউন"),
]


async def create_rehearsal_election(total_voters: int) -> Election:
    async with AsyncSessionLocal() as db:
        # remove a previous rehearsal election (cascade deletes positions, candidates, ballots, votes)
        for old in (await db.execute(select(Election).where(Election.title == REHEARSAL_TITLE))).scalars().all():
            await db.delete(old)
        # only one election may be active
        for other in (await db.execute(select(Election).where(Election.status == ElectionStatus.ACTIVE))).scalars().all():
            other.status = ElectionStatus.COMPLETED
        await db.flush()

        election = Election(
            title=REHEARSAL_TITLE, title_bn=REHEARSAL_TITLE_BN, year=2026,
            description="Sample election with anonymous candidates for testing the scanner pipeline",
            status=ElectionStatus.ACTIVE, dashboard_published=True, dashboard_paused=False,
            total_voters=total_voters,
        )
        db.add(election)
        await db.flush()

        voter_no, name_index = 101, 0
        for pos_data in DEFAULT_POSITIONS:
            position = Position(election_id=election.id, **pos_data)
            db.add(position)
            await db.flush()
            for order in range(6 if pos_data["position_order"] == 13 else 2):
                name_en, name_bn = ANONYMOUS_NAMES[name_index]
                db.add(Candidate(
                    position_id=position.id, election_id=election.id, voter_no=str(voter_no),
                    name_en=name_en, name_bn=name_bn, display_order=order,
                ))
                voter_no += 1
                name_index += 1
        await db.commit()
        return election


async def load_layout(election_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        positions = (await db.execute(
            select(Position).where(Position.election_id == election_id).order_by(Position.position_order)
        )).scalars().all()
        return [{
            "name": p.name_en, "max_selections": p.max_selections,
            "candidates": [{"voter_no": c.voter_no, "name": c.name_en}
                           for c in sorted(p.candidates, key=lambda c: (c.display_order, c.id))],
        } for p in positions]


def write_ballots(positions: list[dict], count: int, overvote: int, violations: bool, seed: int | None) -> list[Path]:
    rng = random.Random(seed)
    out = settings.scanned_path
    # start from an empty folder so the rehearsal is predictable
    for old in out.glob("sample_ballot_*.pdf"):
        old.unlink()
    files = []
    for index in range(1, count + 1):
        marked = random_choices(positions, rng)
        outside, smudged = set(), set()
        if index <= overvote:  # rule (ka): two marks for the first post
            for cand in positions[0]["candidates"]:
                marked.add(cand["voter_no"])
        if violations and index == overvote + 1 and len(positions) > 1:  # rule (kha): X outside the box
            chosen = next(iter(sorted(v for v in marked if v in {c["voter_no"] for c in positions[1]["candidates"]})), None)
            if chosen:
                marked.discard(chosen)
                outside.add(chosen)
        if violations and index == overvote + 2 and len(positions) > 2:  # rule (ga): scribbled box
            chosen = next(iter(sorted(v for v in marked if v in {c["voter_no"] for c in positions[2]["candidates"]})), None)
            if chosen:
                marked.discard(chosen)
                smudged.add(chosen)
        image = draw_ballot(
            positions, marked, skew_degrees=rng.uniform(-1.5, 1.5),
            noise=rng.random() < 0.3, seed=rng.randint(0, 10**6),
            ballot_no=f"{index:04d}", outside=outside, smudged=smudged,
        )
        files.append(save_pdf([image], out / f"sample_ballot_{index:03d}.pdf"))
    return files


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=10, help="number of sample ballots (default 10)")
    parser.add_argument("--overvote", type=int, default=0, help="how many ballots get an over-vote (rule ka)")
    parser.add_argument("--violations", action="store_true", help="also add one 'X outside the box' (rule kha) and one scribbled box (rule ga)")
    parser.add_argument("--voters", type=int, default=500, help="total voters shown on the dashboard")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--ballots-only", action="store_true", help="keep the existing rehearsal election, only write PDFs")
    args = parser.parse_args()

    await init_db()
    await create_default_admin()

    if args.ballots_only:
        async with AsyncSessionLocal() as db:
            election = (await db.execute(select(Election).where(Election.title == REHEARSAL_TITLE))).scalar_one_or_none()
        if not election:
            sys.exit("No rehearsal election found - run without --ballots-only first")
    else:
        election = await create_rehearsal_election(args.voters)
        print(f"Created '{REHEARSAL_TITLE}' (id {election.id}) with 13 positions and 30 anonymous candidates; status active, dashboard published")

    positions = await load_layout(election.id)
    files = write_ballots(positions, args.count, args.overvote, args.violations, args.seed)
    print(f"Wrote {len(files)} sample ballots to {settings.scanned_path}")
    print()
    print("Next: start the system, log in at http://localhost:3000/admin, open Ballots and press")
    print("'Process Scanned folder now'. Watch http://localhost:3000/dashboard update one ballot at a time.")
    if not settings.AUTO_PROCESS_ENABLED:
        print("(AUTO_PROCESS_ENABLED=false in .env: nothing is processed until you press the button.)")
    else:
        print("(AUTO_PROCESS_ENABLED=true in .env: the API will process the files as soon as it starts.)")


if __name__ == "__main__":
    asyncio.run(main())
