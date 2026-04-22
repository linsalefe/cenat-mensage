"""Scheduler de delays do Chatbot.

Loop assíncrono que processa ChatbotScheduledResume pendentes a cada 30s.
Startado pelo lifespan do FastAPI como asyncio.create_task(...).
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.chatbot.engine import resume_session_from_node
from app.database import AsyncSessionLocal
from app.models import ChatbotScheduledResume

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
BATCH_LIMIT = 50


async def run_once() -> None:
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.utcnow()
            res = await db.execute(
                select(ChatbotScheduledResume)
                .where(
                    ChatbotScheduledResume.status == "pending",
                    ChatbotScheduledResume.resume_at <= now,
                )
                .order_by(ChatbotScheduledResume.resume_at)
                .limit(BATCH_LIMIT)
            )
            resumes = res.scalars().all()
            if not resumes:
                return

            logger.info(f"⏰ Chatbot scheduler: {len(resumes)} resume(s) pendente(s)")

            for r in resumes:
                try:
                    ok = await resume_session_from_node(r.session_id, r.node_id, db)
                    r.status = "processed" if ok else "cancelled"
                    r.processed_at = datetime.utcnow()
                    await db.commit()
                except Exception as e:
                    logger.error(f"❌ Resume {r.id} falhou: {e}")
                    try:
                        r.status = "cancelled"
                        r.processed_at = datetime.utcnow()
                        await db.commit()
                    except Exception:
                        await db.rollback()

        except Exception as e:
            logger.error(f"❌ Erro no ciclo do chatbot scheduler: {e}")


async def start_chatbot_scheduler() -> None:
    """Loop infinito — disparado pelo lifespan do FastAPI."""
    print("⏰ Chatbot scheduler loop started (poll 30s)", flush=True)
    logger.info("Chatbot scheduler loop started (poll 30s)")
    while True:
        try:
            await run_once()
        except Exception as e:
            logger.error(f"❌ Erro no loop do chatbot scheduler: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
