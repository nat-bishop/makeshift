from __future__ import annotations

import base64
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
        tags=[Tag.SOLID, Tag.RIGID, Tag.SHARP, Tag.HEAT_SOURCE],
        visual_descriptor=VisualDescriptor(
            base_form="sword",
            material="metal",
            color_primary="#CC3300",
            color_primary_name="fiery red",
            color_secondary="#FF6600",
            color_secondary_name="bright orange",
            visual_effects=["flaming"],
            size_category="medium",
            bg_color="#4A6741",
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
    app.state.remove_bg = AsyncMock(return_value=b"fake_image")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app
    finally:
        await db.close()


async def _create_session(client: AsyncClient) -> str:
    resp = await client.post("/api/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


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
        assert isinstance(data["placeholder_png_base64"], str)
        assert len(data["placeholder_png_base64"]) > 0
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


async def test_create_object_placeholder_is_valid_png() -> None:
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
        png_bytes = base64.b64decode(resp.json()["placeholder_png_base64"])
        assert png_bytes[:4] == b"\x89PNG"


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
