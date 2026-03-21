from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import objects, rules, sessions
from app.ws.handler import websocket_handler

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DATA_DIR = Path(settings.database_path).parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Ensure directories exist
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "sprites").mkdir(exist_ok=True)
    (STATIC_DIR / "placeholders").mkdir(exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize rembg session (loads model once)
    from rembg import new_session

    app.state.rembg_session = new_session(model_name="birefnet-general")

    # Initialize SQLite
    import aiosqlite

    db = await aiosqlite.connect(settings.database_path)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            budget_used REAL NOT NULL DEFAULT 0.0,
            level_progress INTEGER NOT NULL DEFAULT 0
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
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            session_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            object_id TEXT,
            PRIMARY KEY (session_id, slot),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment (
            session_id TEXT NOT NULL,
            slot_name TEXT NOT NULL,
            object_id TEXT,
            PRIMARY KEY (session_id, slot_name),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    await db.commit()
    app.state.db = db

    from app.creator.agent import _get_agent
    _get_agent()  # Warm up LLM agent

    yield

    await db.close()


app = FastAPI(title="LLM Sandbox Game", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
