"""Tests for session CRUD endpoints — V3."""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiosqlite
import pytest
from app.middleware import session_context_middleware
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.models.session import WorldObject
from app.routers import sessions
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


async def _init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    await db.execute("""CREATE TABLE sessions (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
        budget_used REAL NOT NULL DEFAULT 0.0, budget_limit REAL NOT NULL DEFAULT 1.0
    )""")
    await db.execute("""CREATE TABLE objects (
        session_id TEXT NOT NULL, object_id TEXT NOT NULL,
        blueprint_json TEXT NOT NULL, x REAL NOT NULL DEFAULT 0.0,
        y REAL NOT NULL DEFAULT 0.0, durability REAL NOT NULL DEFAULT 0.0,
        PRIMARY KEY (session_id, object_id),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")
    await db.commit()
    return db


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(sessions.router)
    app.middleware("http")(session_context_middleware)
    return app


def _make_blueprint(obj_id: str = "test-obj-1", name: str = "test rock") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=obj_id,
        name=name,
        description="a simple test rock",
        visual_description="a small gray stone rock",
        physics=PhysicsProperties(mass_kg=5.0, height_cm=30, friction=60, bounce=5, gravity=60),
        destructibility=Destructibility(armor=70, hp=80),
        affordance=3,
        autonomous=False,
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    db = await _init_db()
    app = _make_test_app()
    app.state.db = db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await db.close()


async def test_create_session(client: AsyncClient) -> None:
    resp = await client.post("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "rules" not in data  # V3: no rules delivery
    assert data["ws_url"].startswith("ws://")
    assert isinstance(data["budget_remaining"], float)


async def test_get_session(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert "rules" not in data
    assert data["ws_url"].startswith("ws://")


async def test_get_session_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


async def test_sync_session(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    resp = await client.put(f"/api/sessions/{session_id}/sync", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_sync_session_with_objects(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    blueprint = _make_blueprint()
    world_obj = WorldObject(
        object_id=blueprint.id,
        blueprint=blueprint,
        x=100.0,
        y=200.0,
        hp=80.0,
    )

    sync_resp = await client.put(
        f"/api/sessions/{session_id}/sync",
        json={"objects": [world_obj.model_dump(mode="json")]},
    )
    assert sync_resp.status_code == 200

    get_resp = await client.get(f"/api/sessions/{session_id}")
    data = get_resp.json()
    objs = data["session"]["objects"]
    matched = [o for o in objs if o["object_id"] == blueprint.id]
    assert len(matched) == 1
    assert matched[0]["x"] == 100.0
