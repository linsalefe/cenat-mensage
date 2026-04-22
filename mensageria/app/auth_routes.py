"""Rotas de autenticação."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from app.deps import DbSession
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None
    is_admin: bool

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: DbSession) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def register(req: RegisterRequest, db: DbSession) -> UserOut:
    """Bootstrap: só permite criar o PRIMEIRO usuário. Depois, sempre 403."""
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()
    if total > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registro público desabilitado. Use o script create_admin.py.",
        )

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
