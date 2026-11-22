"""Candidates router — CRUD for candidates (any number per position)."""

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Ballot, Candidate, Election, Position
from app.models.admin_user import AdminUser
from app.schemas.candidate import CandidateBulkCreate, CandidateCreate, CandidateResponse, CandidateUpdate
from app.services.events import notifier
from app.utils import audit
from app.utils.security import get_current_user

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])


@router.get("/election/{election_id}", response_model=list[CandidateResponse])
async def list_candidates(election_id: int, db: AsyncSession = Depends(get_db)):
    """All candidates of an election in ballot order."""
    result = await db.execute(
        select(Candidate)
        .join(Position, Candidate.position_id == Position.id)
        .where(Candidate.election_id == election_id)
        .order_by(Position.position_order, Candidate.display_order, Candidate.id)
    )
    return result.scalars().all()


@router.get("/position/{position_id}", response_model=list[CandidateResponse])
async def list_candidates_by_position(position_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Candidate).where(Candidate.position_id == position_id)
        .order_by(Candidate.display_order, Candidate.id)
    )
    return result.scalars().all()


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


async def _validate_position(db: AsyncSession, data: CandidateCreate) -> None:
    result = await db.execute(select(Position).where(Position.id == data.position_id))
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail=f"Position {data.position_id} not found")
    if position.election_id != data.election_id:
        raise HTTPException(status_code=400, detail="Position does not belong to that election")


# Also at the bare prefix: a 307 slash-redirect through the UI proxy loses the Authorization header.
@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    data: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    await _validate_position(db, data)
    candidate = Candidate(**data.model_dump())
    db.add(candidate)
    audit.record(db, current_user.id, "candidate_create", f"Candidate {data.voter_no} '{data.name_en}' added")
    await db.commit()
    await db.refresh(candidate)
    notifier.notify()
    return candidate


@router.post("/bulk", response_model=list[CandidateResponse], status_code=status.HTTP_201_CREATED)
async def create_candidates_bulk(
    data: CandidateBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    candidates = []
    for item in data.candidates:
        await _validate_position(db, item)
        candidate = Candidate(**item.model_dump())
        db.add(candidate)
        candidates.append(candidate)
    audit.record(db, current_user.id, "candidate_bulk_create", f"{len(candidates)} candidates added")
    await db.commit()
    for candidate in candidates:
        await db.refresh(candidate)
    notifier.notify()
    return candidates


@router.post("/import", response_model=list[CandidateResponse], status_code=status.HTTP_201_CREATED)
async def import_candidates_csv(
    election_id: int,
    file: UploadFile = File(...),
    replace: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Load candidates from a CSV file (UTF-8, Excel "CSV UTF-8" works).

    Columns: `voter_no`, `post_no` (the post's serial on the ballot, 1-13),
    `name_en`, optional `name_bn`.  Rows are taken in ballot order.  If the
    election has no positions yet, the 13 standard posts are created first.
    `replace=true` removes the existing candidates (only before counting starts).
    """
    from app.routers.elections import DEFAULT_POSITIONS  # avoid a circular import

    election = (await db.execute(select(Election).where(Election.id == election_id))).scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")

    try:
        text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The file is not UTF-8 text. In Excel use Save As -> 'CSV UTF-8'.")
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    missing = {"voter_no", "post_no", "name_en"} - fields
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing column(s): {', '.join(sorted(missing))}")
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
    rows = [r for r in rows if any(r.values())]
    if not rows:
        raise HTTPException(status_code=400, detail="The file has no candidate rows")

    positions = (await db.execute(select(Position).where(Position.election_id == election_id))).scalars().all()
    if not positions:
        for pos_data in DEFAULT_POSITIONS:
            db.add(Position(election_id=election_id, **pos_data))
        await db.flush()
        positions = (await db.execute(select(Position).where(Position.election_id == election_id))).scalars().all()
    by_order = {p.position_order: p for p in positions}

    existing = (await db.execute(select(Candidate).where(Candidate.election_id == election_id))).scalars().all()
    if replace and existing:
        ballots = (await db.execute(select(func.count(Ballot.id)).where(Ballot.election_id == election_id))).scalar() or 0
        if ballots:
            raise HTTPException(status_code=409, detail="Ballots have already been counted for this election; candidates cannot be replaced")
        for candidate in existing:
            await db.delete(candidate)
        await db.flush()
        existing = []

    taken = {c.voter_no for c in existing}
    next_order: dict[int, int] = {}
    for c in existing:
        next_order[c.position_id] = max(next_order.get(c.position_id, 0), c.display_order + 1)
    errors: list[str] = []
    created: list[Candidate] = []
    for line, row in enumerate(rows, start=2):
        voter_no, name_en = row.get("voter_no", ""), row.get("name_en", "")
        try:
            position = by_order.get(int(row.get("post_no", "")))
        except ValueError:
            position = None
        if not voter_no or not name_en:
            errors.append(f"line {line}: voter_no and name_en are required")
            continue
        if position is None:
            errors.append(f"line {line}: post_no '{row.get('post_no')}' does not match a position of this election")
            continue
        if voter_no in taken:
            errors.append(f"line {line}: voter_no {voter_no} is already used")
            continue
        taken.add(voter_no)
        order = next_order.get(position.id, 0)
        next_order[position.id] = order + 1
        candidate = Candidate(
            election_id=election_id, position_id=position.id, voter_no=voter_no,
            name_en=name_en, name_bn=row.get("name_bn") or None, display_order=order,
        )
        db.add(candidate)
        created.append(candidate)
    if errors:
        await db.rollback()
        raise HTTPException(status_code=400, detail="; ".join(errors[:10]) + (" ..." if len(errors) > 10 else ""))

    audit.record(
        db, current_user.id, "candidate_import",
        f"{len(created)} candidates imported from {file.filename or 'CSV'}" + (" (replaced existing)" if replace else ""),
    )
    await db.commit()
    for candidate in created:
        await db.refresh(candidate)
    notifier.notify()
    return created


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(candidate, key, value)
    audit.record(db, current_user.id, "candidate_update", f"Candidate #{candidate_id}: {changes}")
    await db.commit()
    await db.refresh(candidate)
    notifier.notify()
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    audit.record(db, current_user.id, "candidate_delete", f"Candidate {candidate.voter_no} '{candidate.name_en}' deleted")
    await db.delete(candidate)
    await db.commit()
    notifier.notify()
