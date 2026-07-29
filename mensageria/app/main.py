import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth_routes import router as auth_router
from app.broadcast.worker import start_broadcast_worker
from app.broadcast_cleanup import start_broadcast_cleanup_task
from app.campaign.routes import router as campaign_router
from app.campaign.worker import start_campaign_worker
from app.chatbot.routes import router as chatbot_router
from app.chatbot.scheduler import start_chatbot_scheduler
from app.agent.workers import (
    start_agent_conversion_worker,
    start_agent_followup_worker,
    start_agent_sync_worker,
)
from app.broadcast_routes import router as broadcast_router
from app.contact_lists.routes import router as contact_lists_router
from app.contact_tags_routes import router as contact_tags_router
from app.contacts_routes import router as contacts_router
from app.dashboard_routes import router as dashboard_router
from app.documents.routes import router as documents_router
from app.groups_routes import router as groups_router
from app.media_routes import router as media_router
from app.profile_routes import router as profile_router
from app.users_routes import router as users_router
from app.config import get_settings
from app.database import AsyncSessionLocal, engine
from app.evolution.routes import (
    router as evolution_router,
    webhook_router as evolution_webhook_router,
)
from app.meta.routes import (
    router as meta_router,
    webhook_router as meta_webhook_router,
    bridge_router as meta_bridge_router,
)
from app.instagram.routes import (
    router as instagram_router,
    webhook_router as instagram_webhook_router,
)
from app.crm.routes import router as crm_router
from app.crm.routes import bridge_router as crm_bridge_router
from app.payments.routes import router as payments_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_task = asyncio.create_task(start_chatbot_scheduler())
    cleanup_task = asyncio.create_task(start_broadcast_cleanup_task())
    worker_task = asyncio.create_task(start_broadcast_worker())
    campaign_task = asyncio.create_task(start_campaign_worker())
    # Agente de IA (Fase 3): sync sempre; conversão/follow-up gated por agent_enabled.
    agent_sync_task = asyncio.create_task(start_agent_sync_worker())
    agent_conv_task = asyncio.create_task(start_agent_conversion_worker())
    agent_fu_task = asyncio.create_task(start_agent_followup_worker())
    try:
        yield
    finally:
        for t in (scheduler_task, cleanup_task, worker_task, campaign_task,
                  agent_sync_task, agent_conv_task, agent_fu_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        await engine.dispose()


app = FastAPI(
    title="mensageria",
    description="Backend CENAT de mensageria (evolution/chatbot/automations)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(evolution_router)
app.include_router(evolution_webhook_router)
app.include_router(meta_webhook_router)
app.include_router(meta_bridge_router)
app.include_router(meta_router)
app.include_router(instagram_webhook_router)
app.include_router(instagram_router)
app.include_router(crm_router)
app.include_router(crm_bridge_router)
app.include_router(payments_router)
app.include_router(chatbot_router)
app.include_router(contacts_router)
app.include_router(contact_tags_router)
app.include_router(media_router)
app.include_router(documents_router)
app.include_router(groups_router)
app.include_router(broadcast_router)
app.include_router(contact_lists_router)
app.include_router(campaign_router)
app.include_router(users_router)
app.include_router(profile_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = "connected"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc.__class__.__name__}"
    return {"status": "ok", "db": db_status}
