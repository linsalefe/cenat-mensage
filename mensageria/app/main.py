import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth_routes import router as auth_router
from app.broadcast_cleanup import start_broadcast_cleanup_task
from app.chatbot.routes import router as chatbot_router
from app.chatbot.scheduler import start_chatbot_scheduler
from app.broadcast_routes import router as broadcast_router
from app.contacts_routes import router as contacts_router
from app.dashboard_routes import router as dashboard_router
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

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_task = asyncio.create_task(start_chatbot_scheduler())
    cleanup_task = asyncio.create_task(start_broadcast_cleanup_task())
    try:
        yield
    finally:
        for t in (scheduler_task, cleanup_task):
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
app.include_router(chatbot_router)
app.include_router(contacts_router)
app.include_router(media_router)
app.include_router(groups_router)
app.include_router(broadcast_router)
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
