#!/usr/bin/env python
"""Cria um usuário admin no banco.

Uso:
    python scripts/create_admin.py <email> <senha> <nome>

Cria um User com is_admin=True, mesmo que já existam outros usuários.
"""
import asyncio
import sys
from pathlib import Path

# Permite rodar como script solto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.auth import hash_password
from app.database import AsyncSessionLocal
from app.models import User


async def main(email: str, password: str, name: str) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"❌ Usuário com email {email!r} já existe.", file=sys.stderr)
            sys.exit(1)

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name,
            is_active=True,
            is_admin=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"✅ Admin criado: id={user.id} email={user.email} name={user.name!r}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python scripts/create_admin.py <email> <senha> <nome>", file=sys.stderr)
        sys.exit(2)

    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
