"""Tests for WebSocket handler: connection lifecycle, ping/pong, broadcast functions."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from app.ws.handler import (
    _connections,
    send_sprite_failed,
    send_sprite_ready,
    websocket_handler,
)
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    await db.execute(
        "INSERT INTO sessions (id, created_at, budget_limit)"
        " VALUES ('test-session', '2024-01-01', 1.0)"
    )
    await db.commit()
    app.state.db = db
    yield
    await db.close()


def _make_test_app() -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    @app.websocket("/ws/{session_id}")
    async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
        await websocket_handler(websocket, session_id)

    return app


@pytest.fixture(autouse=True)
def _clear_connections() -> Iterator[None]:
    _connections.clear()
    yield
    _connections.clear()


def test_ws_connect_invalid_session() -> None:
    app = _make_test_app()
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):  # noqa: SIM117
        with client.websocket_connect("/ws/nonexistent") as ws:
            ws.receive_json()


def test_ws_ping_pong() -> None:
    app = _make_test_app()
    with TestClient(app) as client, client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data == {"type": "pong"}


def test_ws_unknown_message() -> None:
    app = _make_test_app()
    with TestClient(app) as client, client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "foo"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "foo" in data["message"]


def test_ws_connection_cleanup() -> None:
    app = _make_test_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/test-session"):
            assert "test-session" in _connections
        assert "test-session" not in _connections


async def test_send_sprite_ready_broadcast() -> None:
    mock_ws = AsyncMock()
    _connections["test-session"] = {mock_ws}
    await send_sprite_ready("test-session", "obj-1", "/static/sprites/abc123.png")
    mock_ws.send_json.assert_called_once()
    msg = mock_ws.send_json.call_args[0][0]
    assert msg["type"] == "sprite_ready"
    assert msg["object_id"] == "obj-1"
    assert msg["sprite_url"] == "/static/sprites/abc123.png"


async def test_send_sprite_failed_broadcast() -> None:
    mock_ws = AsyncMock()
    _connections["test-session"] = {mock_ws}
    await send_sprite_failed("test-session", "obj-1", "generation timed out")
    mock_ws.send_json.assert_called_once()
    msg = mock_ws.send_json.call_args[0][0]
    assert msg["type"] == "sprite_failed"
    assert msg["object_id"] == "obj-1"
    assert msg["reason"] == "generation timed out"


async def test_broadcast_multiple_clients() -> None:
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    ws3 = AsyncMock()
    _connections["test-session"] = {ws1, ws2, ws3}
    await send_sprite_ready("test-session", "obj-1", "/static/sprites/abc.png")
    for mock_ws in (ws1, ws2, ws3):
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "sprite_ready"
        assert msg["object_id"] == "obj-1"
