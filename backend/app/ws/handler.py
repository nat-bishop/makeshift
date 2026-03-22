from __future__ import annotations

import base64
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.sessions.manager import SessionManager

logger = logging.getLogger(__name__)

# Active connections: session_id → set of WebSocket
_connections: dict[str, set[WebSocket]] = {}


async def websocket_handler(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for server→client sprite delivery and events.

    Client→Server: ping (keepalive)
    Server→Client: sprite_ready, error
    """
    db = websocket.app.state.db
    manager = SessionManager(db)

    # Verify session exists before accepting
    session = await manager.get_session(session_id)
    if session is None:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # Register connection for sprite delivery (multi-client)
    _connections.setdefault(session_id, set()).add(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up connection
        ws_set = _connections.get(session_id, set())
        ws_set.discard(websocket)
        if not ws_set:
            _connections.pop(session_id, None)


async def _broadcast(session_id: str, message: dict[str, object]) -> None:
    """Send a JSON message to all connected clients for a session."""
    ws_set = _connections.get(session_id, set())
    for ws in list(ws_set):
        try:
            await ws.send_json(message)
        except Exception:
            logger.warning("WebSocket send failed for session %s", session_id)
            ws_set.discard(ws)


async def send_sprite_ready(
    session_id: str,
    object_id: str,
    sprite_bytes: bytes,
    width: int,
    height: int,
) -> None:
    """Push a sprite to all connected clients for a session."""
    sprite_b64 = base64.b64encode(sprite_bytes).decode()
    await _broadcast(session_id, {
        "type": "sprite_ready",
        "object_id": object_id,
        "sprite_png_base64": sprite_b64,
        "width": width,
        "height": height,
    })


async def send_error(session_id: str, error_message: str) -> None:
    """Send an error message to all connected clients."""
    await _broadcast(session_id, {"type": "error", "message": error_message})
