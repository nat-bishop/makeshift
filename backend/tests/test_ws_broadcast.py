"""Tests for WebSocket broadcast functions and _handle_request_sprite."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.ws.handler import (
    _broadcast,
    _connections,
    _handle_request_sprite,
    send_behaviors_ready,
    send_cache_ready,
    send_cache_updated,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _clear_connections() -> Iterator[None]:
    _connections.clear()
    yield
    _connections.clear()


# ---------------------------------------------------------------------------
# Broadcast functions: send_cache_ready, send_behaviors_ready, send_cache_updated
# ---------------------------------------------------------------------------


async def test_send_cache_ready() -> None:
    ws = AsyncMock()
    _connections["s1"] = {ws}
    entries = [{"name_a": "fire", "name_b": "wood", "effects": []}]
    await send_cache_ready("s1", "fire", entries)
    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg == {
        "type": "cache_ready",
        "object_name": "fire",
        "entries": entries,
    }


async def test_send_behaviors_ready() -> None:
    ws = AsyncMock()
    _connections["s1"] = {ws}
    behaviors = [{"trigger": "ALWAYS", "action": "WANDER", "target": "SELF"}]
    await send_behaviors_ready("s1", "wolf", behaviors)
    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg == {
        "type": "behaviors_ready",
        "creature_name": "wolf",
        "behaviors": behaviors,
    }


async def test_send_cache_updated() -> None:
    ws = AsyncMock()
    _connections["s1"] = {ws}
    entries = [{"name_a": "ice", "name_b": "fire", "effects": []}]
    await send_cache_updated("s1", entries)
    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg == {
        "type": "cache_updated",
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Error tolerance: broken client removed, others still receive
# ---------------------------------------------------------------------------


async def test_broadcast_tolerates_send_failure() -> None:
    good_ws = AsyncMock()
    bad_ws = AsyncMock()
    bad_ws.send_json.side_effect = RuntimeError("connection lost")

    _connections["s1"] = {good_ws, bad_ws}

    await _broadcast("s1", {"type": "test", "data": 1})

    # Good client received the message
    good_ws.send_json.assert_called_once_with({"type": "test", "data": 1})
    # Bad client was removed from connections
    assert bad_ws not in _connections["s1"]
    assert good_ws in _connections["s1"]


# ---------------------------------------------------------------------------
# _handle_request_sprite
# ---------------------------------------------------------------------------


def _mock_websocket() -> AsyncMock:
    """Create a mock websocket with app.state.db."""
    ws = AsyncMock()
    ws.app = MagicMock()
    ws.app.state.db = MagicMock()
    return ws


@patch("app.ws.handler.SessionManager")
@patch("app.ws.handler.get_cached_sprite_path")
@patch("app.ws.handler.build_prompt")
async def test_handle_request_sprite_cached(
    mock_build_prompt: MagicMock,
    mock_get_cached: MagicMock,
    mock_session_mgr_cls: MagicMock,
) -> None:
    """Sprite on disk -> sends sprite_ready message."""
    ws = _mock_websocket()

    blueprint = MagicMock()
    blueprint.name = "fire sword"
    blueprint.visual_description = "a flaming blade"

    manager_instance = AsyncMock()
    manager_instance.get_object_blueprint.return_value = blueprint
    mock_session_mgr_cls.return_value = manager_instance

    mock_build_prompt.return_value = "test prompt"

    cache_path = MagicMock(spec=Path)
    cache_path.exists.return_value = True
    cache_path.name = "abc123.png"
    mock_get_cached.return_value = cache_path

    await _handle_request_sprite(ws, "s1", "obj-1")

    ws.send_json.assert_called_once()
    msg = ws.send_json.call_args[0][0]
    assert msg == {
        "type": "sprite_ready",
        "object_id": "obj-1",
        "sprite_url": "/static/sprites/abc123.png",
    }


@patch("app.ws.handler.SessionManager")
async def test_handle_request_sprite_no_blueprint(
    mock_session_mgr_cls: MagicMock,
) -> None:
    """No blueprint found -> returns silently, no message sent."""
    ws = _mock_websocket()

    manager_instance = AsyncMock()
    manager_instance.get_object_blueprint.return_value = None
    mock_session_mgr_cls.return_value = manager_instance

    await _handle_request_sprite(ws, "s1", "obj-missing")

    ws.send_json.assert_not_called()


@patch("app.ws.handler.SessionManager")
@patch("app.ws.handler.get_cached_sprite_path")
@patch("app.ws.handler.build_prompt")
async def test_handle_request_sprite_not_on_disk(
    mock_build_prompt: MagicMock,
    mock_get_cached: MagicMock,
    mock_session_mgr_cls: MagicMock,
) -> None:
    """Blueprint exists but sprite not on disk -> returns silently."""
    ws = _mock_websocket()

    blueprint = MagicMock()
    blueprint.name = "ice shield"
    blueprint.visual_description = "a frozen barrier"

    manager_instance = AsyncMock()
    manager_instance.get_object_blueprint.return_value = blueprint
    mock_session_mgr_cls.return_value = manager_instance

    mock_build_prompt.return_value = "test prompt"

    cache_path = MagicMock(spec=Path)
    cache_path.exists.return_value = False
    mock_get_cached.return_value = cache_path

    await _handle_request_sprite(ws, "s1", "obj-2")

    ws.send_json.assert_not_called()
