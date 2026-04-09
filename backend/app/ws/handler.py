from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.images.pipeline import build_prompt, get_cached_sprite_path
from app.sessions.manager import SessionManager

if TYPE_CHECKING:
    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()

# Active connections: session_id → set of WebSocket
_connections: dict[str, set[WebSocket]] = {}

# Background tasks must be held to prevent GC before completion
_background_tasks: set[asyncio.Task[None]] = set()


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
                        _handle_state_changed(websocket, session_id, object_name)
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

    prompt = build_prompt(blueprint.name, blueprint.visual_description)
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


async def _handle_state_changed(websocket: WebSocket, session_id: str, object_name: str) -> None:
    """Re-evaluate pairwise + creature behaviors for a changed object."""
    from app.cache.scene import SceneCache
    from app.engine.creature import evaluate_creature_behaviors
    from app.engine.pairwise import evaluate_pair

    scenes: dict = websocket.app.state.scenes
    scene = scenes.setdefault(session_id, SceneCache())
    cache = websocket.app.state.cache

    # Invalidate stale creature behaviors for this target
    scene.mark_creature_stale_for_target(object_name)

    # Invalidate stale pairwise entries involving this object
    stale_keys = scene.mark_stale(object_name)

    db = websocket.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        return

    from app.cache.store import normalize_name

    target_norm = normalize_name(object_name)
    creatures = []
    changed_bp = None
    bp_by_name: dict[str, GameObjectBlueprint] = {}
    for obj in session.objects:
        bp = obj.blueprint
        bp_by_name[normalize_name(bp.name)] = bp
        if normalize_name(bp.name) == target_norm:
            changed_bp = bp
        if bp.autonomous:
            creatures.append(bp)

    if changed_bp is None:
        return

    # If the changed object is itself a creature, invalidate its outgoing behaviors
    if changed_bp.autonomous:
        scene.mark_creature_stale_for_creature(object_name)

    scene_names = [obj.blueprint.name for obj in session.objects]

    # Re-evaluate stale pairwise pairs in background
    async def _reeval_pairwise() -> None:
        if not stale_keys:
            return
        reeval_tasks = []
        for key in stale_keys:
            a_name, b_name = key.split("::")
            bp_a = bp_by_name.get(a_name)
            bp_b = bp_by_name.get(b_name)
            if bp_a is not None and bp_b is not None:
                reeval_tasks.append(evaluate_pair(bp_a, bp_b, cache, scene))

        if not reeval_tasks:
            return
        results = await asyncio.gather(*reeval_tasks, return_exceptions=True)
        await cache.flush()

        entries = []
        for key, result in zip(stale_keys, results, strict=False):
            if isinstance(result, BaseException):
                logger.warning("pairwise_reeval_failed", key=key, error=str(result))
                continue
            entry = result.to_dict()
            a_name, b_name = key.split("::")
            entry["name_a"] = a_name
            entry["name_b"] = b_name
            entries.append(entry)
        if entries:
            await send_cache_updated(session_id, entries)

    # Re-evaluate creature behaviors toward the changed object
    async def _reeval_creatures() -> None:
        if not creatures:
            return

        async def _eval_one(creature_bp):
            behaviors = await evaluate_creature_behaviors(
                creature_bp, [changed_bp], scene_names, scene
            )
            if behaviors:
                from app.routers.objects import _format_behaviors

                await send_behaviors_ready(
                    session_id, creature_bp.name, _format_behaviors(behaviors)
                )

        await asyncio.gather(*[_eval_one(c) for c in creatures], return_exceptions=True)

    # Re-evaluate changed creature's behaviors toward all scene objects
    async def _reeval_changed_creature() -> None:
        if not changed_bp.autonomous:
            return
        targets = [bp_by_name[n] for n in bp_by_name if n != target_norm]
        if not targets:
            return
        behaviors = await evaluate_creature_behaviors(changed_bp, targets, scene_names, scene)
        if behaviors:
            from app.routers.objects import _format_behaviors

            await send_behaviors_ready(session_id, changed_bp.name, _format_behaviors(behaviors))

    await asyncio.gather(
        _reeval_pairwise(),
        _reeval_creatures(),
        _reeval_changed_creature(),
        return_exceptions=True,
    )


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


async def send_cache_ready(session_id: str, object_name: str, entries: list[dict]) -> None:
    """Deliver pairwise cache entries to clients after spawn integration."""
    logger.info(
        "send_cache_ready",
        session_id=session_id,
        object_name=object_name,
        entry_count=len(entries),
    )
    await _broadcast(
        session_id,
        {
            "type": "cache_ready",
            "object_name": object_name,
            "entries": entries,
        },
    )


async def send_behaviors_ready(session_id: str, creature_name: str, behaviors: list[dict]) -> None:
    """Deliver creature behavior entries to clients."""
    logger.info(
        "send_behaviors_ready",
        session_id=session_id,
        creature_name=creature_name,
        behavior_count=len(behaviors),
    )
    await _broadcast(
        session_id,
        {
            "type": "behaviors_ready",
            "creature_name": creature_name,
            "behaviors": behaviors,
        },
    )


async def send_cache_updated(session_id: str, entries: list[dict]) -> None:
    """Deliver re-evaluated pairwise cache entries after state change."""
    logger.info(
        "send_cache_updated",
        session_id=session_id,
        entry_count=len(entries),
    )
    await _broadcast(
        session_id,
        {
            "type": "cache_updated",
            "entries": entries,
        },
    )
