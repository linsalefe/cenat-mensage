"""Cliente da API pública da Doity (somente leitura).

⚠️ Particularidades confirmadas em 29/07/2026 (ver AUDITORIA.md / memória doity-api-shape):
- NÃO existe endpoint de listagem de eventos — acesso só por event-id conhecido.
- `GET /eventos/{id}` (detalhe) retorna 404 para este token, mesmo documentado.
  Por isso NÃO usamos detalhe: preços vêm de `/eventos/{id}/lotes`; conversões de
  `/eventos/{id}/participantes`. Nome/datas do evento vivem em agent_products (seed).
- Lotes vêm com `termino.data=null` — o prazo do lote mora no seed, não na API.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import get_settings

settings = get_settings()


class DoityError(RuntimeError):
    def __init__(self, status: int, body: str = ""):
        self.status = status
        super().__init__(f"Doity HTTP {status}: {body[:200]}")


class DoityClient:
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        self.token = token or settings.DOITY_TOKEN
        self.base = (base_url or settings.DOITY_BASE_URL).rstrip("/")

    def _headers(self) -> dict:
        return {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.get(f"{self.base}{path}", headers=self._headers(), params=params)
        if r.status_code != 200:
            raise DoityError(r.status_code, r.text)
        return r.json()

    async def get_lotes(self, event_id: int) -> list[dict]:
        data = await self._get(f"/eventos/{event_id}/lotes", {"limit": 50})
        return data.get("lotes", []) or []

    async def get_campos_personalizados(self, event_id: int) -> list[dict]:
        data = await self._get(f"/eventos/{event_id}/campos_personalizados")
        return data.get("campos_personalizados", []) or []

    async def get_participantes(
        self,
        event_id: int,
        data_atualizacao: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        sort: str = "modified",
        direction: str = "asc",
        ativo: int = 1,
    ) -> dict:
        """Retorna {participantes:[...], pagination:{...}}.

        `data_atualizacao` (ex.: "2026-07-29 12:00:00") filtra por atualização —
        base do polling de conversão (Fase 3). Se o sort=modified der 500, o
        chamador deve reter e tentar sem sort (mesmo hack do testar_doity.py).
        """
        params: dict[str, Any] = {
            "ativo": ativo, "page": page, "limit": limit,
            "sort": sort, "direction": direction,
        }
        if data_atualizacao:
            params["data_atualizacao"] = data_atualizacao
        return await self._get(f"/eventos/{event_id}/participantes", params)
