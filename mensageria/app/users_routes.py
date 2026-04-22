"""Gestão de usuários (admin-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import CurrentUser, get_current_user, hash_password
from app.deps import DbSession
from app.models import User

router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)],
)


class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    name: str | None = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class ResetPassword(BaseModel):
    new_password: str = Field(..., min_length=8)


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "is_active": u.is_active,
        "is_admin": u.is_admin,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


def _require_admin(current_user: CurrentUser) -> None:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores",
        )


@router.get("")
async def list_users(db: DbSession, current_user: CurrentUser):
    _require_admin(current_user)
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    return [_user_to_dict(u) for u in res.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, db: DbSession, current_user: CurrentUser):
    _require_admin(current_user)

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        is_active=True,
        is_admin=data.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_to_dict(user)


@router.patch("/{user_id}")
async def update_user(
    user_id: int, data: UserUpdate, db: DbSession, current_user: CurrentUser
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Bloqueios de auto-mutação
    if user.id == current_user.id:
        if data.is_active is False:
            raise HTTPException(
                status_code=400,
                detail="Você não pode se desativar",
            )
        if data.is_admin is False:
            raise HTTPException(
                status_code=400,
                detail="Você não pode remover seu próprio admin",
            )

    if data.name is not None:
        user.name = data.name
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_admin is not None:
        user.is_admin = data.is_admin

    await db.commit()
    await db.refresh(user)
    return _user_to_dict(user)


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: ResetPassword,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.password_hash = hash_password(data.new_password)
    await db.commit()
    print(f"🔑 Admin {current_user.email} resetou senha de {user.email}")
    return {"status": "ok", "user_id": user.id}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, current_user: CurrentUser):
    _require_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode se auto-excluir")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    await db.delete(user)
    await db.commit()
