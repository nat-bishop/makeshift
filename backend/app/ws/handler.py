from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.images.pipeline import get_cached_sprite_path
from app.prompts.image import build_text_to_image_prompt
from app.sessions.manager import SessionManager

if TYPE_CHECKING:
    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()

# Active connections: session_id → set of WebSocket
_connections: dict[str, set[WebSocket]] = {}

# Background tasks must be held to prevent GC before completion
_background_tasks: set[asyncio.Task[None]] = set()


async def websocket_handler(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for server→client delivery and events.

    Client→Server: ping, state_changed, request_sprite
    Server→Client: sprite_ready, behaviors_ready, behavior_updated
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
            elif msg_type == "state_changed":
                object_name = data.get("object_name", "")
                active_states = data.get("active_states", [])
                if object_name:
                    logger.info(
                        "ws_state_changed",
                        session_id=session_id,
                        object_name=object_name,
                        states=active_states,
                    )
                    task = asyncio.create_task(
                        _handle_state_changed(websocket, session_id, object_name, active_states)
                    )
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)
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


async def _handle_request_sprite(websocket: WebSocket, session_id: str, object_id: str) -> None:
    """Check if a sprite exists on disk and re-send sprite_ready if so."""
    db = websocket.app.state.db
    manager = SessionManager(db)
    blueprint = await manager.get_object_blueprint(session_id, object_id)
    if blueprint is None:
        logger.debug("request_sprite_not_found", session_id=session_id, object_id=object_id)
        return

    prompt = build_text_to_image_prompt(blueprint.name, blueprint.visual_description)
    cache_path = get_cached_sprite_path(prompt)
    if not cache_path.exists():
        logger.debug("request_sprite_not_ready", session_id=session_id, object_id=object_id)
        return

    sprite_url = f"/static/sprites/{cache_path.name}"
    logger.info("request_sprite_fulfilled", session_id=session_id, object_id=object_id)
    await websocket.send_json(
        {
            "type": "sprite_ready",
            "object_id": object_id,
            "sprite_url": sprite_url,
        }
    )


async def _handle_state_changed(
    websocket: WebSocket, session_id: str, object_name: str, active_states: list[int]
) -> None:
    """Re-evaluate behaviors for objects affected by a state change.

    Invalidates all behavioral entries involving the changed object,
    then re-evaluates behaviors with current state context.
    """
    from app.cache.scene import BehaviorCache
    from app.cache.store import normalize_name
    from app.engine.behavior import evaluate_behaviors

    scenes: dict = websocket.app.state.scenes
    scene = scenes.setdefault(session_id, BehaviorCache())

    db = websocket.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        return

    from app.models.blueprint import PLAYER_BLUEPRINT

    target_norm = normalize_name(object_name)
    changed_bp: GameObjectBlueprint | None = None
    bp_by_name: dict[str, GameObjectBlueprint] = {}
    for obj in session.objects:
        bp = obj.blueprint
        bp_by_name[normalize_name(bp.name)] = bp
        if normalize_name(bp.name) == target_norm:
            changed_bp = bp

    # Always include player so creature re-evaluations can reference it
    bp_by_name[normalize_name(PLAYER_BLUEPRINT.name)] = PLAYER_BLUEPRINT
    if target_norm == normalize_name(PLAYER_BLUEPRINT.name):
        changed_bp = PLAYER_BLUEPRINT

    if changed_bp is None:
        return

    # Invalidate all behavioral entries involving the changed object
    stale_keys = scene.invalidate_behavior(object_name)

    target_states: dict[str, list[int]] = {object_name: active_states}

    # Find all objects that HAD behavior entries toward the changed object
    # and re-evaluate them. stale_keys are "a::b" format.
    reactors: set[str] = set()
    for key in stale_keys:
        parts = key.split("::")
        for part in parts:
            if part != target_norm:
                reactors.add(part)

    cache = websocket.app.state.cache
    from app.engine.projectile import trigger_projectile_generation

    async def _reeval(reactor_name: str) -> None:
        reactor_bp = bp_by_name.get(reactor_name)
        if reactor_bp is None:
            return
        behaviors = await evaluate_behaviors(
            reactor_bp,
            [changed_bp],
            scene,
            target_states=target_states,
        )
        if behaviors:
            entries = format_behaviors(reactor_bp.name, behaviors)
            await send_behavior_updated(session_id, reactor_bp.name, entries)
            trigger_projectile_generation(session_id, entries, cache, _background_tasks)

    # Re-evaluate the changed object's own outgoing behaviors (only stale targets)
    async def _reeval_changed() -> None:
        # Only re-evaluate targets that had stale entries from this object
        changed_targets: set[str] = set()
        for key in stale_keys:
            parts = key.split("::")
            # directed key: subject::target. If subject is the changed object, target is stale
            if len(parts) == 2 and parts[0] == target_norm:
                changed_targets.add(parts[1])
        target_bps = [bp_by_name[n] for n in changed_targets if n in bp_by_name]
        if not target_bps:
            return
        behaviors = await evaluate_behaviors(
            changed_bp,
            target_bps,
            scene,
        )
        if behaviors:
            entries = format_behaviors(changed_bp.name, behaviors)
            await send_behavior_updated(session_id, changed_bp.name, entries)
            trigger_projectile_generation(session_id, entries, cache, _background_tasks)

    tasks = [_reeval(name) for name in reactors]
    tasks.append(_reeval_changed())
    await asyncio.gather(*tasks, return_exceptions=True)


def format_behaviors(
    subject_name: str,
    behaviors: dict,
) -> list[dict]:
    """Format behavior entries for WS delivery."""
    from app.cache.store import normalize_name

    entries = []
    for target_name, entry in behaviors.items():
        d = entry.to_dict()
        d["subject_name"] = normalize_name(subject_name)
        d["target_name"] = normalize_name(target_name)
        entries.append(d)
    return entries


# ---- Broadcast helpers ----


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


async def send_sprite_ready(session_id: str, object_id: str, sprite_url: str) -> None:
    """Notify clients that a sprite is ready."""
    logger.info("send_sprite_ready", session_id=session_id, object_id=object_id)
    await _broadcast(
        session_id,
        {
            "type": "sprite_ready",
            "object_id": object_id,
            "sprite_url": sprite_url,
        },
    )


async def send_combined_sprite_ready(session_id: str, object_id: str, sprite_url: str) -> None:
    """Notify clients that a carry/ride combined sprite is ready."""
    logger.info("send_combined_sprite_ready", session_id=session_id, object_id=object_id)
    await _broadcast(
        session_id,
        {
            "type": "combined_sprite_ready",
            "object_id": object_id,
            "sprite_url": sprite_url,
        },
    )


async def send_destruction_sprite_ready(
    session_id: str,
    object_id: str,
    destruction_result_name: str,
    sprite_url: str,
) -> None:
    """Notify clients that a pre-generated destruction debris sprite is ready."""
    logger.info(
        "send_destruction_sprite_ready",
        session_id=session_id,
        object_id=object_id,
        debris=destruction_result_name,
    )
    await _broadcast(
        session_id,
        {
            "type": "destruction_sprite_ready",
            "object_id": object_id,
            "destruction_result_name": destruction_result_name,
            "sprite_url": sprite_url,
        },
    )


async def send_sprite_failed(session_id: str, object_id: str, reason: str = "") -> None:
    """Notify clients that sprite generation failed."""
    logger.warning("send_sprite_failed", session_id=session_id, object_id=object_id, reason=reason)
    await _broadcast(
        session_id,
        {
            "type": "sprite_failed",
            "object_id": object_id,
            "reason": reason,
        },
    )


async def send_behaviors_ready(session_id: str, subject_name: str, behaviors: list[dict]) -> None:
    """Deliver behavior entries to clients after spawn integration."""
    logger.info("send_behaviors_ready", session_id=session_id, subject=subject_name)
    await _broadcast(
        session_id,
        {
            "type": "behaviors_ready",
            "subject_name": subject_name,
            "behaviors": behaviors,
        },
    )


async def send_behavior_updated(session_id: str, subject_name: str, behaviors: list[dict]) -> None:
    """Deliver re-evaluated behavioral entries after state change."""
    logger.info("send_behavior_updated", session_id=session_id, subject=subject_name)
    await _broadcast(
        session_id,
        {
            "type": "behavior_updated",
            "subject_name": subject_name,
            "behaviors": behaviors,
        },
    )


async def send_projectile_ready(session_id: str, projectile: dict) -> None:
    """Deliver a freshly generated ProjectileBlueprint so the client can spawn
    it on demand when an ObjectBehavior fires a ranged attack."""
    logger.info(
        "send_projectile_ready",
        session_id=session_id,
        name=projectile.get("name"),
    )
    await _broadcast(
        session_id,
        {
            "type": "projectile_ready",
            "projectile": projectile,
        },
    )
