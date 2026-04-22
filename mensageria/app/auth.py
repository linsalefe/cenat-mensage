"""Auth: hash bcrypt, JWT HS256, get_current_user."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select

from app.config import get_settings
from app.deps import DbSession
from app.models import User

settings = get_settings()

ALGORITHM = "HS256"
DEFAULT_EXPIRES_MINUTES = 60 * 24 * 7  # 7 dias

# bcrypt tem limite de 72 bytes no secret — truncamos para evitar ValueError em 4.x
_BCRYPT_MAX = 72


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw = plain.encode("utf-8")[:_BCRYPT_MAX]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, expires_minutes: int = DEFAULT_EXPIRES_MINUTES) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise _credentials_error()
        return int(sub)
    except (JWTError, ValueError):
        raise _credentials_error()


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise _credentials_error()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _credentials_error()
    return token


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = _extract_bearer(authorization)
    user_id = decode_token(token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _credentials_error()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
