"""Perfil do usuário logado — PATCH nome + trocar senha."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import CurrentUser, get_current_user, hash_password, verify_password
from app.deps import DbSession
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/profile",
    tags=["Profile"],
    dependencies=[Depends(get_current_user)],
)


class ProfileUpdate(BaseModel):
    name: str | None = None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "is_active": u.is_active,
        "is_admin": u.is_admin,
    }


@router.patch("")
async def update_profile(
    data: ProfileUpdate, db: DbSession, current_user: CurrentUser
):
    res = await db.execute(select(User).where(User.id == current_user.id))
    user = res.scalar_one()
    if data.name is not None:
        user.name = data.name
    await db.commit()
    await db.refresh(user)
    return _user_to_dict(user)


@router.post("/change-password")
async def change_password(
    data: ChangePassword, db: DbSession, current_user: CurrentUser
):
    res = await db.execute(select(User).where(User.id == current_user.id))
    user = res.scalar_one()
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta",
        )

    user.password_hash = hash_password(data.new_password)
    await db.commit()

    ts = datetime.now(timezone.utc).isoformat()
    print(f"🔐 {ts} — senha alterada por {user.email} (id={user.id})", flush=True)
    logger.info(f"Password changed by user {user.email} (id={user.id})")

    return {"status": "ok"}
