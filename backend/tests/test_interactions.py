"""Tests for collision rule query endpoint."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import aiosqlite
from app.cache.scene import BehaviorCache, CollisionRule
from app.cache.store import CacheStore
from app.middleware import session_context_middleware
from app.models.blueprint import GameObjectBlueprint, PhysicsProperties
from app.routers import interactions, sessions
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(session_context_middleware)
    app.include_router(sessions.router)
    app.include_router(interactions.router)
    return app


def _make_blueprint(name: str = "fire sword") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=name,
        description=f"a {name}",
        visual_description=f"a glowing {name} with intricate details",
        physics=PhysicsProperties(mass_kg=1.5, height_cm=120, surface=1, bounce=10, gravity=50),
        durability=4,
        affordance=0,
        autonomous=False,
    )


@asynccontextmanager
async def _test_client() -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    app = _make_app()
    db = await aiosqlite.connect(":memory:")
    await db.execute("""CREATE TABLE sessions (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
        budget_used REAL NOT NULL DEFAULT 0.0,
        budget_limit REAL NOT NULL DEFAULT 1.0
    )""")
    await db.execute("""CREATE TABLE objects (
        session_id TEXT NOT NULL, object_id TEXT NOT NULL,
        blueprint_json TEXT NOT NULL, x REAL NOT NULL DEFAULT 0.0,
        y REAL NOT NULL DEFAULT 0.0, durability REAL NOT NULL DEFAULT 0.0,
        states_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (session_id, object_id),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")
    await db.commit()
    app.state.db = db

    cache = await CacheStore.open(":memory:")
    app.state.cache = cache
    app.state.scenes = {}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, app
    finally:
        await cache.close()
        await db.close()


async def _create_session(client: AsyncClient) -> str:
    resp = await client.post("/api/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


async def _insert_object(
    db: aiosqlite.Connection, session_id: str, bp: GameObjectBlueprint
) -> None:
    await db.execute(
        "INSERT INTO objects (session_id, object_id, blueprint_json) VALUES (?, ?, ?)",
        (session_id, bp.id, bp.model_dump_json()),
    )
    await db.commit()


def _assert_no_force(data: dict) -> None:
    assert data["force_on_b"] == 0
    assert data["cached"] is False


# ---- GET /scene tests ----


async def test_get_scene_valid_session_returns_cached_pairs() -> None:
    async with _test_client() as (client, app):
        session_id = await _create_session(client)
        db = app.state.db

        bp_a = _make_blueprint("sword")
        bp_b = _make_blueprint("shield")
        await _insert_object(db, session_id, bp_a)
        await _insert_object(db, session_id, bp_b)

        # Seed a collision cache entry for this pair
        cache: CacheStore = app.state.cache
        pair_data = {
            "force_on_b": 30,
        }
        await cache.put_collision("shield", "sword", pair_data)

        resp = await client.get(f"/api/sessions/{session_id}/interactions/scene")
        assert resp.status_code == 200
        data = resp.json()
        assert "pairs" in data
        assert len(data["pairs"]) == 1
        key = next(iter(data["pairs"].keys()))
        assert data["pairs"][key]["force_on_b"] == 30


async def test_get_scene_invalid_session_returns_empty() -> None:
    async with _test_client() as (client, _app):
        resp = await client.get("/api/sessions/nonexistent/interactions/scene")
        assert resp.status_code == 200
        assert resp.json() == {"pairs": {}}


# ---- POST /interactions tests ----


async def test_post_interaction_success() -> None:
    async with _test_client() as (client, app):
        session_id = await _create_session(client)
        db = app.state.db

        bp_a = _make_blueprint("sword")
        bp_b = _make_blueprint("shield")
        await _insert_object(db, session_id, bp_a)
        await _insert_object(db, session_id, bp_b)

        # Set up a BehaviorCache for this session
        scene = BehaviorCache()
        app.state.scenes[session_id] = scene

        mock_result = CollisionRule(force_on_b=30)

        with patch(
            "app.routers.interactions.evaluate_collision",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(
                f"/api/sessions/{session_id}/interactions",
                json={"name_a": "sword", "name_b": "shield"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["force_on_b"] == 30
        assert data["cached"] is True


async def test_post_interaction_missing_session_returns_no_force() -> None:
    async with _test_client() as (client, app):
        # Scene exists but session not in DB — hits the session-missing branch
        fake_id = "no-such-session"
        app.state.scenes[fake_id] = BehaviorCache()

        resp = await client.post(
            f"/api/sessions/{fake_id}/interactions",
            json={"name_a": "sword", "name_b": "shield"},
        )

        assert resp.status_code == 200
        _assert_no_force(resp.json())


async def test_post_interaction_missing_scene_returns_no_force() -> None:
    async with _test_client() as (client, _app):
        session_id = await _create_session(client)

        resp = await client.post(
            f"/api/sessions/{session_id}/interactions",
            json={"name_a": "sword", "name_b": "shield"},
        )

        assert resp.status_code == 200
        # Scene gets auto-created, but session lookup may fail to find objects
        _assert_no_force(resp.json())


async def test_post_interaction_unknown_object_returns_no_force() -> None:
    async with _test_client() as (client, app):
        session_id = await _create_session(client)
        db = app.state.db

        bp_a = _make_blueprint("sword")
        await _insert_object(db, session_id, bp_a)
        app.state.scenes[session_id] = BehaviorCache()

        resp = await client.post(
            f"/api/sessions/{session_id}/interactions",
            json={"name_a": "sword", "name_b": "unknown thing"},
        )

        assert resp.status_code == 200
        _assert_no_force(resp.json())
