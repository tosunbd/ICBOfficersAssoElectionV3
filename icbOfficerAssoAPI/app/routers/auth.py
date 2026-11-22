"""Authentication router — login, current user, password change."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import AdminUserResponse, ChangePasswordRequest, LoginRequest, TokenResponse
from app.utils import audit
from app.utils.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate an admin user and return a JWT token."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == request.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    audit.record(db, user.id, "login", f"{user.username} signed in")
    await db.commit()
    token = create_access_token({"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=AdminUserResponse)
async def get_me(current_user: AdminUser = Depends(get_current_user)):
    return current_user


@router.put("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = hash_password(data.new_password)
    audit.record(db, current_user.id, "password_change", f"{current_user.username} changed password")
    await db.commit()
    return {"status": "ok"}
