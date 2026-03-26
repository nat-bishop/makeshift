from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_setup import setup_logging
from app.middleware import session_context_middleware
from app.routers import objects, rules, sessions
from app.ws.handler import websocket_handler

logger = structlog.get_logger()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DATA_DIR = Path(settings.database_path).parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()

    # Optionally enable Logfire observability
    if settings.logfire_enabled:
        import logfire

        logfire.configure(service_name="makeshift")
        logfire.instrument_fastapi(app)
        logfire.instrument_pydantic_ai()
        logger.info("logfire_enabled")

    logger.info(
        "server_starting",
        llm_model=settings.llm_model,
        image_model=settings.image_model,
        image_backend=settings.image_backend,
        bg_removal=settings.bg_removal_backend,
        budget=settings.session_budget_usd,
    )

    # Ensure directories exist
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "sprites").mkdir(exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize background removal callable
    if settings.bg_removal_backend == "local":
        from app.images.gpu_bg import make_gpu_remover

        app.state.remove_bg = make_gpu_remover()
    else:
        from app.images.cloud_bg import make_cloud_remover

        app.state.remove_bg = make_cloud_remover()

    # Initialize image generation callable
    if settings.image_backend == "local":
        from app.images.local_image import generate_image

        app.state.generate_image = generate_image
        logger.info("image_backend_local", url=settings.local_image_url)
    elif settings.image_backend == "fal":
        from app.images.fal_image import generate_image

        app.state.generate_image = generate_image
        logger.info("image_backend_fal")
    else:
        from app.images.gemini_client import generate_image

        app.state.generate_image = generate_image
        logger.info("image_backend_gemini")

    # Initialize SQLite
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
    app.state.db = db

    from app.creator.agent import _get_agent

    _get_agent()  # Warm up LLM agent
    logger.info("llm_agent_ready")

    yield

    logger.info("server_stopping")

    from app.images.fal_helpers import close_http_client as close_fal_client
    from app.images.local_image import close_http_client as close_local_client

    await close_fal_client()
    await close_local_client()
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
app.include_router(rules.router)


# WebSocket endpoint
@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket_handler(websocket, session_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
