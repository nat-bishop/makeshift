"""Tests for session CRUD endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiosqlite
import pytest
from app.middleware import session_context_middleware
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.session import WorldObject
from app.models.tags import Tag
from app.routers import sessions
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


async def _init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    await db.execute("""CREATE TABLE sessions (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
        budget_used REAL NOT NULL DEFAULT 0.0, budget_limit REAL NOT NULL DEFAULT 1.0,
        current_level INTEGER NOT NULL DEFAULT 1,
        levels_completed TEXT NOT NULL DEFAULT '[]'
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


def _make_blueprint(obj_id: str = "test-obj-1", name: str = "Test Rock") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=obj_id,
        name=name,
        description="A simple test rock",
        tags=[Tag.SOLID, Tag.RIGID],
        visual_descriptor=VisualDescriptor(
            base_form="rock",
            material="stone",
            color_primary="#888888",
            color_primary_name="gray",
            color_secondary="#666666",
            color_secondary_name="dark gray",
            visual_effects=[],
            size_category="small",
            bg_color="#4A6B8A",
        ),
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    db = await _init_db()
    app = _make_test_app()
    app.state.db = db
    app.state.remove_bg = lambda x: x
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
    assert len(data["seed_objects"]) == 15
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) > 0
    assert data["ws_url"].startswith("ws://")
    assert isinstance(data["budget_remaining"], float)


async def test_get_session(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert isinstance(data["rules"], list)
    assert data["ws_url"].startswith("ws://")
    assert isinstance(data["budget_remaining"], float)


async def test_get_session_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


async def test_sync_session(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    resp = await client.put(f"/api/sessions/{session_id}/sync", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_sync_session_not_found(client: AsyncClient) -> None:
    resp = await client.put("/api/sessions/nonexistent/sync", json={})
    assert resp.status_code == 404


async def test_sync_session_with_objects(client: AsyncClient) -> None:
    create_resp = await client.post("/api/sessions")
    session_id = create_resp.json()["session_id"]

    blueprint = _make_blueprint()
    world_obj = WorldObject(
        object_id=blueprint.id,
        blueprint=blueprint,
        x=100.0,
        y=200.0,
        durability=150.0,
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
    assert matched[0]["y"] == 200.0
