"""Auth de serviço (Sprint S1 — Ponte do Mensage).

O Customer chama o Mensage por HTTP enviando o header ``X-Service-Token``.
Aqui vivem:

- ``require_service_token``: dependency que exige o service-token (403 se faltar
  ou não bater). Usada nos endpoints que SÓ o Customer chama.
- ``get_user_or_service``: dependency que aceita **ou** JWT de usuário **ou**
  ``X-Service-Token``. Retorna o ``User`` (chamada de usuário) ou ``None``
  (chamada de serviço). Usada na ponte de broadcast pra não quebrar a auth de
  usuário já existente.

Comparação sempre constant-time (``hmac.compare_digest``). Nunca logar o valor.
"""
from __future__ import annotations

import hmac
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from app.auth import get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.models import User

_settings = get_settings()


def _service_token_ok(x_service_token: Optional[str]) -> bool:
    """True só se o token foi enviado, está configurado e bate (constant-time)."""
    if not x_service_token or not _settings.SERVICE_TOKEN:
        return False
    return hmac.compare_digest(x_service_token, _settings.SERVICE_TOKEN)


async def require_service_token(
    x_service_token: Annotated[Optional[str], Header()] = None,
) -> None:
    """Exige o service-token. 403 se faltar ou não bater."""
    if not _settings.SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SERVICE_TOKEN não configurado",
        )
    if not _service_token_ok(x_service_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Service-Token inválido ou ausente",
        )


async def get_user_or_service(
    db: DbSession,
    authorization: Annotated[Optional[str], Header()] = None,
    x_service_token: Annotated[Optional[str], Header()] = None,
) -> Optional[User]:
    """Aceita JWT de usuário OU X-Service-Token.

    - Service-token válido  -> retorna ``None`` (chamada de serviço/Customer).
    - Caso contrário        -> exige o JWT de usuário (``get_current_user``),
      que levanta 401 se ausente/ inválido.
    """
    if _service_token_ok(x_service_token):
        return None
    return await get_current_user(db, authorization)


UserOrService = Annotated[Optional[User], Depends(get_user_or_service)]
