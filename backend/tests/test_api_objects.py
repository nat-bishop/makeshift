from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import aiosqlite
from app.middleware import session_context_middleware
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag
from app.routers import objects, sessions
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(session_context_middleware)
    app.include_router(sessions.router)
    app.include_router(objects.router)
    return app


def _make_blueprint() -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name="Fire Sword",
        description="a fire sword",
        tags=[Tag.RIGID, Tag.SHARP, Tag.HEAT_SOURCE],
        visual_descriptor=VisualDescriptor(
            visual_description="a curved steel sword with a fiery red blade wreathed in flames",
            size_category="medium",
        ),
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
        PRIMARY KEY (session_id, object_id),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")
    await db.commit()
    app.state.db = db
    # Mock pipeline singletons so background sprite task doesn't hit real backends.
    import app.images.pipeline as _pipeline

    orig_gen, orig_bg = _pipeline._generate_image, _pipeline._remove_bg
    _pipeline._generate_image = AsyncMock(return_value=b"fake_image")
    _pipeline._remove_bg = AsyncMock(return_value=b"fake_image")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app
    finally:
        _pipeline._generate_image = orig_gen
        _pipeline._remove_bg = orig_bg
        await db.close()


async def _create_session(client: AsyncClient) -> str:
    resp = await client.post("/api/sessions")
    assert resp.status_code == 200
    session_id: str = resp.json()["session_id"]
    return session_id


async def test_create_object_success() -> None:
    async with _test_client() as (client, _app):
        session_id = await _create_session(client)
        with patch(
            "app.routers.objects.create_object", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = _make_blueprint()
            resp = await client.post(
                f"/api/sessions/{session_id}/objects",
                json={"description": "fire sword"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "blueprint" in data
        assert "budget_remaining" in data


async def test_create_object_session_not_found() -> None:
    async with _test_client() as (client, _app):
        with patch(
            "app.routers.objects.create_object", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = _make_blueprint()
            resp = await client.post(
                "/api/sessions/nonexistent/objects",
                json={"description": "fire sword"},
            )
        assert resp.status_code == 404


async def test_create_object_budget_exceeded() -> None:
    async with _test_client() as (client, app):
        session_id = await _create_session(client)
        db = app.state.db
        await db.execute(
            "UPDATE sessions SET budget_used = budget_limit WHERE id = ?",
            (session_id,),
        )
        await db.commit()

        with patch(
            "app.routers.objects.create_object", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = _make_blueprint()
            resp = await client.post(
                f"/api/sessions/{session_id}/objects",
                json={"description": "fire sword"},
            )
        assert resp.status_code == 402


async def test_create_object_blueprint_structure() -> None:
    async with _test_client() as (client, _app):
        session_id = await _create_session(client)
        with patch(
            "app.routers.objects.create_object", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = _make_blueprint()
            resp = await client.post(
                f"/api/sessions/{session_id}/objects",
                json={"description": "fire sword"},
            )
        blueprint = resp.json()["blueprint"]
        for key in ("id", "name", "tags", "visual_descriptor", "description", "behaviors"):
            assert key in blueprint, f"Missing key: {key}"
