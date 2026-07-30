"""Status do agente de IA para o frontend (somente leitura).

Existe por um motivo só: a tela de Conversas precisa avisar o atendente quando o
agente está em MODO SANDBOX, porque nesse estado o canal pode estar com
`agent_enabled=true` e mesmo assim a IA não responder a quase ninguém — sem o
aviso, isso parece bug.

**Não expõe os números da allowlist.** São telefones de pessoas reais; o
frontend só precisa saber SE o sandbox está ligado e QUANTOS contatos ele cobre.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth import get_current_user
from app.config import get_settings
from app.deps import DbSession
from app.agent.phone import parse_allowlist
from app.models import Channel

router = APIRouter(
    prefix="/api/agent",
    tags=["Agent"],
    dependencies=[Depends(get_current_user)],
)

settings = get_settings()


@router.get("/status")
async def agent_status(db: DbSession) -> dict:
    """Modo do agente + em quais canais ele está ligado.

    `channels_enabled` deixa a tela distinguir "IA desligada em tudo" de "IA
    ligada, mas este contato está fora do sandbox".
    """
    entradas = parse_allowlist(settings.AGENT_TEST_WA_ALLOWLIST)
    habilitados = list(
        (await db.execute(select(Channel.id).where(Channel.agent_enabled.is_(True))))
        .scalars()
        .all()
    )
    return {
        "sandbox": bool(entradas),
        "sandbox_count": len(entradas),  # nunca os números em si
        "channels_enabled": habilitados,
    }
