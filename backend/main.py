"""
Phantom TG Harvester — FastAPI Backend Entry Point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import init_db
from .routers import dashboard, accounts, parser, sender, inviter, chat_finder, media, tiktok, license, system

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup and reset stale running tasks."""
    await init_db()
    try:
        from .database import get_db
        db = await get_db()
        await db.execute("UPDATE send_tasks SET status = 'stopped' WHERE status = 'running'")
        await db.execute("UPDATE invite_tasks SET status = 'stopped' WHERE status = 'running'")
        await db.commit()
        await db.close()
    except Exception:
        pass
    yield

app = FastAPI(
    title="Phantom TG Harvester",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Web (Vercel), Electron, and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard.router)
app.include_router(accounts.router)
app.include_router(parser.router)
app.include_router(sender.router)
app.include_router(inviter.router)
app.include_router(chat_finder.router)
app.include_router(media.router)
app.include_router(tiktok.router)
app.include_router(license.router)
app.include_router(system.router)


@app.get("/")
async def root():
    return {"name": "Phantom TG Harvester", "version": "1.0.0", "status": "running"}
