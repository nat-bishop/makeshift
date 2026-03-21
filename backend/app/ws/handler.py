from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from app.sessions.manager import SessionManager


async def websocket_handler(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for server→client sprite delivery and events.

    Client→Server: ping (keepalive)
    Server→Client: sprite_ready, error
    """
    db = websocket.app.state.db
    manager = SessionManager(db)

    # Verify session exists
    session = await manager.get_session(session_id)
    if session is None:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # Register connection for sprite delivery
    if not hasattr(websocket.app.state, "ws_connections"):
        websocket.app.state.ws_connections = {}
    websocket.app.state.ws_connections[session_id] = websocket

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
        connections: dict = getattr(websocket.app.state, "ws_connections", {})
        connections.pop(session_id, None)
