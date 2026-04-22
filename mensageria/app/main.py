import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth_routes import router as auth_router
from app.chatbot.routes import router as chatbot_router
from app.chatbot.scheduler import start_chatbot_scheduler
from app.contacts_routes import router as contacts_router
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
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
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


@app.get("/health")
async def health() -> dict[str, str]:
    db_status = "connected"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc.__class__.__name__}"
    return {"status": "ok", "db": db_status}
