from __future__ import annotations

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.images.pipeline import build_prompt, get_cached_sprite_path
from app.sessions.manager import SessionManager

logger = structlog.get_logger()

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
    if not await manager.session_exists(session_id):
        logger.warning("ws_rejected", session_id=session_id, reason="not_found")
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # Register connection for sprite delivery (multi-client)
    _connections.setdefault(session_id, set()).add(websocket)
    logger.info(
        "ws_connected",
        session_id=session_id,
        connection_count=len(_connections[session_id]),
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "request_sprite":
                object_id = data.get("object_id", "")
                if object_id:
                    await _handle_request_sprite(websocket, session_id, object_id)
            elif msg_type == "reevaluate_creature":
                creature_id = data.get("creature_id", "")
                reason = data.get("reason", "")
                if creature_id:
                    await _handle_reevaluate_creature(
                        websocket, session_id, creature_id, reason
                    )
            else:
                logger.warning("ws_unknown_message_type", msg_type=msg_type)
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    }
                )
    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=session_id)
    finally:
        # Clean up connection
        ws_set = _connections.get(session_id, set())
        ws_set.discard(websocket)
        remaining = len(ws_set)
        if not ws_set:
            _connections.pop(session_id, None)
        logger.info(
            "ws_connection_cleaned_up",
            session_id=session_id,
            remaining_connections=remaining,
        )


async def _handle_request_sprite(
    websocket: WebSocket, session_id: str, object_id: str
) -> None:
    """Check if a sprite exists on disk and re-send sprite_ready if so."""
    db = websocket.app.state.db
    manager = SessionManager(db)
    blueprint = await manager.get_object_blueprint(session_id, object_id)
    if blueprint is None:
        logger.debug("request_sprite_not_found", session_id=session_id, object_id=object_id)
        return

    prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
    cache_path = get_cached_sprite_path(prompt)
    if not cache_path.exists():
        logger.debug("request_sprite_not_ready", session_id=session_id, object_id=object_id)
        return

    sprite_url = f"/static/sprites/{cache_path.name}"
    logger.info("request_sprite_fulfilled", session_id=session_id, object_id=object_id)
    await websocket.send_json({
        "type": "sprite_ready",
        "object_id": object_id,
        "sprite_url": sprite_url,
    })


async def _broadcast(session_id: str, message: dict[str, object]) -> None:
    """Send a JSON message to all connected clients for a session."""
    ws_set = _connections.get(session_id, set())
    logger.debug(
        "ws_broadcast",
        session_id=session_id,
        msg_type=message.get("type"),
        recipient_count=len(ws_set),
    )
    for ws in list(ws_set):
        try:
            await ws.send_json(message)
        except Exception:
            logger.error("ws_send_failed", session_id=session_id, exc_info=True)
            ws_set.discard(ws)


async def send_sprite_ready(
    session_id: str,
    object_id: str,
    sprite_url: str,
) -> None:
    """Notify clients that a sprite is ready and where to fetch it."""
    logger.info(
        "send_sprite_ready",
        session_id=session_id,
        object_id=object_id,
        sprite_url=sprite_url,
    )
    msg: dict[str, object] = {
        "type": "sprite_ready",
        "object_id": object_id,
        "sprite_url": sprite_url,
    }
    await _broadcast(session_id, msg)


async def send_sprite_failed(session_id: str, object_id: str, reason: str = "") -> None:
    """Notify clients that sprite generation failed for an object."""
    logger.warning(
        "send_sprite_failed",
        session_id=session_id,
        object_id=object_id,
        reason=reason,
    )
    await _broadcast(
        session_id,
        {
            "type": "sprite_failed",
            "object_id": object_id,
            "reason": reason,
        },
    )


async def send_pairwise_ready(
    session_id: str, pair_key: str, result: dict[str, object]
) -> None:
    """Notify clients that a pairwise interaction result is ready."""
    logger.info("send_pairwise_ready", session_id=session_id, pair_key=pair_key)
    await _broadcast(
        session_id,
        {
            "type": "pairwise_ready",
            "pair_key": pair_key,
            "result": result,
        },
    )


async def send_creature_behaviors(
    session_id: str, creature_id: str, behaviors: list[dict]
) -> None:
    """Notify clients of creature behavior evaluation results."""
    logger.info(
        "send_creature_behaviors",
        session_id=session_id,
        creature_id=creature_id,
        behavior_count=len(behaviors),
    )
    await _broadcast(
        session_id,
        {
            "type": "creature_behaviors",
            "creature_id": creature_id,
            "behaviors": behaviors,
        },
    )


async def _handle_reevaluate_creature(
    websocket: WebSocket, session_id: str, creature_id: str, reason: str
) -> None:
    """Handle creature re-evaluation request from client."""
    from app.engine.creature_behavior import evaluate_creature_behaviors

    db = websocket.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if not session:
        return

    # Find the creature and scene objects
    creature_bp = None
    scene_bps = []
    scene_names = []
    for obj in session.objects:
        bp = obj.blueprint.model_dump()
        if obj.object_id == creature_id:
            creature_bp = bp
        else:
            scene_bps.append(bp)
            scene_names.append(bp["name"])

    if creature_bp is None or not creature_bp.get("autonomous"):
        return

    scene_names.append(creature_bp["name"])
    logger.info(
        "reevaluate_creature",
        creature_id=creature_id,
        reason=reason,
        scene_size=len(scene_bps),
    )

    try:
        behaviors = await evaluate_creature_behaviors(creature_bp, scene_bps, scene_names)
        behavior_dicts = [
            {
                "target_name": b.target_name,
                "movement": b.movement,
                "strength": b.strength,
                "action": b.action,
                "action_param": b.action_param,
            }
            for b in behaviors
        ]
        await send_creature_behaviors(session_id, creature_id, behavior_dicts)
    except Exception as exc:
        logger.error("creature_reevaluation_failed", creature_id=creature_id, error=str(exc))
