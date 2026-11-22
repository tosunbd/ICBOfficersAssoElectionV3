"""Elections router — elections and their positions."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Candidate, Election, Position
from app.models.admin_user import AdminUser
from app.models.election import ElectionStatus
from app.schemas.election import (
    ElectionCreate, ElectionDetailResponse, ElectionResponse, ElectionUpdate,
    PositionCreate, PositionResponse, PositionUpdate,
)
from app.services.events import notifier
from app.utils import audit
from app.utils.security import get_current_user

router = APIRouter(prefix="/api/elections", tags=["Elections"])

# The 13 posts printed on the ICB ballot, in ballot order.
DEFAULT_POSITIONS = [
    {"position_order": 1, "name_en": "President", "name_bn": "সভাপতি", "max_selections": 1},
    {"position_order": 2, "name_en": "Vice President", "name_bn": "সহ-সভাপতি", "max_selections": 1},
    {"position_order": 3, "name_en": "General Secretary", "name_bn": "সাধারণ সম্পাদক", "max_selections": 1},
    {"position_order": 4, "name_en": "Asst. General Secretary", "name_bn": "সহকারী সাধারণ সম্পাদক", "max_selections": 1},
    {"position_order": 5, "name_en": "Treasurer", "name_bn": "কোষাধ্যক্ষ", "max_selections": 1},
    {"position_order": 6, "name_en": "Organizing Secretary", "name_bn": "সাংগঠনিক সম্পাদক", "max_selections": 1},
    {"position_order": 7, "name_en": "Office Secretary", "name_bn": "দপ্তর সম্পাদক", "max_selections": 1},
    {"position_order": 8, "name_en": "Publication Secretary", "name_bn": "প্রকাশনা সম্পাদক", "max_selections": 1},
    {"position_order": 9, "name_en": "Cultural Secretary", "name_bn": "সাংস্কৃতিক সম্পাদক", "max_selections": 1},
    {"position_order": 10, "name_en": "Drama Secretary", "name_bn": "নাট্য সম্পাদক", "max_selections": 1},
    {"position_order": 11, "name_en": "Sports Secretary", "name_bn": "ক্রীড়া সম্পাদক", "max_selections": 1},
    {"position_order": 12, "name_en": "Hospitality Secretary", "name_bn": "আপ্যায়ন সম্পাদক", "max_selections": 1},
    {"position_order": 13, "name_en": "Executive Member", "name_bn": "নির্বাহী সদস্য", "max_selections": 3},
]

# Placeholder candidates exactly as printed on the sample ballot (2 per post,
# 6 for Executive Member).  Useful for rehearsals and for testing the scanner.
TEMPLATE_CANDIDATES_BN = [
    "জনাব এবি", "জনাব সিডি", "জনাব বিই", "জনাব ডিসি", "জনাব এমএন", "জনাব বিডি",
    "জনাব সবি", "জনাব নবা", "জনাব মনা", "জনাব জবা", "জনাব পল", "জনাব মট",
    "জনাব খব", "জনাব দথ", "জনাব বগ", "জনাব ইব", "জনাব যব", "জনাব ডগ",
    "জনাব তথ", "জনাব ডচ", "জনাব ডক", "জনাব চছ", "জনাব জঝ", "জনাব গ্রহ",
    "জনাব দত", "জনাব কদ", "জনাব পত", "জনাব রল", "জনাব যস", "জনাব শদ",
]


async def _get_election(db: AsyncSession, election_id: int) -> Election:
    result = await db.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")
    return election


# Also at the bare prefix: a 307 slash-redirect through the UI proxy loses the Authorization header.
@router.get("", response_model=list[ElectionResponse], include_in_schema=False)
@router.get("/", response_model=list[ElectionResponse])
async def list_elections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Election).order_by(Election.year.desc(), Election.id.desc()))
    return result.scalars().all()


@router.get("/{election_id}", response_model=ElectionDetailResponse)
async def get_election(election_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_election(db, election_id)


# Also at the bare prefix: a 307 slash-redirect through the UI proxy loses the Authorization header.
@router.post("", response_model=ElectionResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=ElectionResponse, status_code=status.HTTP_201_CREATED)
async def create_election(
    data: ElectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    election = Election(**data.model_dump())
    db.add(election)
    await db.flush()
    audit.record(db, current_user.id, "election_create", f"Election #{election.id} '{election.title}' created")
    await db.commit()
    await db.refresh(election)
    return election


@router.put("/{election_id}", response_model=ElectionResponse)
async def update_election(
    election_id: int,
    data: ElectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    election = await _get_election(db, election_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ElectionStatus.ALL:
        raise HTTPException(status_code=400, detail=f"status must be one of {list(ElectionStatus.ALL)}")
    for key, value in changes.items():
        setattr(election, key, value)
    audit.record(db, current_user.id, "election_update", f"Election #{election_id}: {changes}")
    await db.commit()
    await db.refresh(election)
    notifier.notify()
    return election


@router.delete("/{election_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_election(
    election_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    election = await _get_election(db, election_id)
    audit.record(db, current_user.id, "election_delete", f"Election #{election_id} '{election.title}' deleted")
    await db.delete(election)
    await db.commit()
    notifier.notify()


# --- Positions ------------------------------------------------------------
@router.post("/{election_id}/seed-positions", response_model=ElectionDetailResponse)
async def seed_default_positions(
    election_id: int,
    with_template_candidates: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """Create the 13 standard ICB positions (optionally with the placeholder
    candidates printed on the sample ballot)."""
    election = await _get_election(db, election_id)
    if election.positions:
        raise HTTPException(status_code=400, detail="Positions already exist for this election")

    voter_no = 101
    name_index = 0
    for pos_data in DEFAULT_POSITIONS:
        position = Position(election_id=election_id, **pos_data)
        db.add(position)
        await db.flush()
        if with_template_candidates:
            count = 6 if pos_data["position_order"] == 13 else 2
            for order in range(count):
                db.add(Candidate(
                    position_id=position.id,
                    election_id=election_id,
                    voter_no=str(voter_no),
                    name_en=f"Candidate {voter_no}",
                    name_bn=TEMPLATE_CANDIDATES_BN[name_index] if name_index < len(TEMPLATE_CANDIDATES_BN) else None,
                    display_order=order,
                ))
                voter_no += 1
                name_index += 1

    audit.record(
        db, current_user.id, "positions_seed",
        f"Election #{election_id}: default positions seeded" + (" with template candidates" if with_template_candidates else ""),
    )
    await db.commit()
    db.expire_all()
    return await _get_election(db, election_id)


@router.post("/{election_id}/positions", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def add_position(
    election_id: int,
    data: PositionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    await _get_election(db, election_id)
    position = Position(election_id=election_id, **data.model_dump())
    db.add(position)
    audit.record(db, current_user.id, "position_create", f"Election #{election_id}: position '{data.name_en}' added")
    await db.commit()
    await db.refresh(position)
    return position


@router.put("/{election_id}/positions/{position_id}", response_model=PositionResponse)
async def update_position(
    election_id: int,
    position_id: int,
    data: PositionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Position).where(Position.id == position_id, Position.election_id == election_id)
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(position, key, value)
    audit.record(db, current_user.id, "position_update", f"Position #{position_id}: {changes}")
    await db.commit()
    await db.refresh(position)
    notifier.notify()
    return position


@router.delete("/{election_id}/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    election_id: int,
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Position).where(Position.id == position_id, Position.election_id == election_id)
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    audit.record(db, current_user.id, "position_delete", f"Position #{position_id} '{position.name_en}' deleted")
    await db.delete(position)
    await db.commit()
    notifier.notify()
