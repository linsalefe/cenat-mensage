"""Limpeza periódica de broadcast_logs — retenção 7 dias.

Rodado por background task no lifespan: 1ª execução 10min após boot,
depois a cada 24h.
"""
import asyncio
import logging

from sqlalchemy import text

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

RETENTION_DAYS = 7
FIRST_RUN_DELAY_SECONDS = 600
INTERVAL_SECONDS = 86400


async def cleanup_old_broadcast_logs() -> int:
    """Apaga broadcast_logs com sent_at mais antigo que RETENTION_DAYS.

    Retorna quantos registros foram removidos.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "DELETE FROM mensageria.broadcast_logs "
                "WHERE sent_at < NOW() - INTERVAL '7 days'"
            )
        )
        await db.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info(f"🧹 broadcast cleanup: {deleted} log(s) removido(s)")
        return deleted


async def start_broadcast_cleanup_task() -> None:
    """Loop de limpeza agendado."""
    print(
        f"🧹 Broadcast cleanup task scheduled (first run in "
        f"{FIRST_RUN_DELAY_SECONDS}s, interval {INTERVAL_SECONDS}s)",
        flush=True,
    )
    logger.info("Broadcast cleanup task scheduled")
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            await cleanup_old_broadcast_logs()
        except Exception as e:
            logger.error(f"❌ Broadcast cleanup falhou: {e}")
        await asyncio.sleep(INTERVAL_SECONDS)
