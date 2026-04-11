"""FastAPI application — V3 with unified behavior system."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_setup import setup_logging
from app.middleware import session_context_middleware
from app.routers import interactions, objects, sessions
from app.ws.handler import websocket_handler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DATA_DIR = Path(settings.database_path).parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()

    if settings.logfire_enabled:
        import logfire

        logfire.configure(service_name="makeshift")
        logfire.instrument_fastapi(app)
        logfire.instrument_pydantic_ai()
        logger.info("logfire_enabled")

    logger.info(
        "server_starting",
        llm_model=settings.llm_model,
        local_llm_url=settings.local_llm_url,
        image_model=settings.image_model,
        image_backend=settings.image_backend,
        bg_removal=settings.bg_removal_backend,
        budget=settings.session_budget_usd,
    )

    # Ensure directories exist
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "sprites").mkdir(exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Warm up image pipeline singletons
    from app.images.pipeline import get_generate_image, get_remove_bg

    get_generate_image()
    get_remove_bg()

    # Initialize game.db (sessions + objects)
    import aiosqlite

    db = await aiosqlite.connect(settings.database_path)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            budget_used REAL NOT NULL DEFAULT 0.0,
            budget_limit REAL NOT NULL DEFAULT 1.0
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS objects (
            session_id TEXT NOT NULL,
            object_id TEXT NOT NULL,
            blueprint_json TEXT NOT NULL,
            x REAL NOT NULL DEFAULT 0.0,
            y REAL NOT NULL DEFAULT 0.0,
            durability REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (session_id, object_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    await db.commit()

    # Migration: add states_json column if not present
    import sqlite3

    try:
        await db.execute("ALTER TABLE objects ADD COLUMN states_json TEXT NOT NULL DEFAULT '[]'")
        await db.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    app.state.db = db

    # Initialize cache.db (creation + pairwise caches, separate from game.db)
    from app.cache.store import CacheStore

    cache_path = str(DATA_DIR / "cache.db")
    cache = await CacheStore.open(cache_path)
    app.state.cache = cache
    app.state.scenes = {}  # session_id -> SceneCache (in-memory, per-session)
    logger.info("cache_db_initialized", path=cache_path)

    logger.info("server_ready")

    yield

    logger.info("server_stopping")

    from app.images.fal_helpers import close_http_client as close_fal_client
    from app.images.local_image import close_http_client as close_local_client

    await close_fal_client()
    await close_local_client()
    await cache.close()
    await db.close()


app = FastAPI(title="Makeshift", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(session_context_middleware)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "sprites").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include routers
app.include_router(sessions.router)
app.include_router(objects.router)
app.include_router(interactions.router)


# WebSocket endpoint
@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket_handler(websocket, session_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
