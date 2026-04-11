"""Object creation endpoint — V3 pipeline with collision + behavior integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.sessions.manager import SessionManager
from app.ws.handler import (
    send_behaviors_ready,
    send_collision_ready,
    send_sprite_failed,
    send_sprite_ready,
)

if TYPE_CHECKING:
    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions/{session_id}/objects", tags=["objects"])

OBJECT_CREATION_COST = 0.041

_background_tasks: set[asyncio.Task[Any]] = set()


class CreateObjectRequest(BaseModel):
    description: str = Field(max_length=500)


class CreateObjectResponse(BaseModel):
    blueprint: dict
    budget_remaining: float


@router.post("", response_model=CreateObjectResponse)
async def create_object_endpoint(
    session_id: str, body: CreateObjectRequest, request: Request
) -> CreateObjectResponse:
    """Create a new game object from a text description.

    Returns the blueprint immediately.
    Sprite generation + collision/behavior integration happen async via background tasks.
    """
    db = request.app.state.db
    manager = SessionManager(db)
    cache = request.app.state.cache

    # Atomically reserve budget
    success, budget_remaining = await manager.reserve_budget(session_id, OBJECT_CREATION_COST)
    if not success:
        if budget_remaining < 0:
            raise HTTPException(status_code=404, detail="Session not found")
        raise HTTPException(status_code=402, detail="Session budget exceeded")

    logger.info("object_create_request", description_len=len(body.description))

    # Create object via V3 pipeline
    from app.creator.pipeline import create_object

    blueprint = await create_object(body.description, cache)

    # Save object to session
    await manager.save_object(session_id, blueprint)

    # Schedule background tasks: sprite gen + collision/behavior integration
    scenes = request.app.state.scenes
    task = asyncio.create_task(_background_spawn(session_id, blueprint, manager, cache, scenes))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Pre-cache destruction result in background
    if blueprint.destruction_result_name:
        debris_task = asyncio.create_task(
            _precache_destruction_debris(blueprint.destruction_result_name, cache)
        )
        _background_tasks.add(debris_task)
        debris_task.add_done_callback(_background_tasks.discard)

    return CreateObjectResponse(
        blueprint=blueprint.model_dump(mode="json"),
        budget_remaining=budget_remaining,
    )


async def _background_spawn(
    session_id: str,
    blueprint: GameObjectBlueprint,
    manager: SessionManager,
    cache: Any,
    scenes: dict,
) -> None:
    """Background: sprite gen + collision screening/eval + creature behavior."""
    logger.info("background_spawn_start", name=blueprint.name)
    results = await asyncio.gather(
        _generate_and_deliver_sprite(session_id, blueprint),
        _run_spawn_integration(session_id, blueprint, manager, cache, scenes),
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        logger.error("background_spawn_failed", name=blueprint.name, errors=errors)
    else:
        logger.info("background_spawn_complete", name=blueprint.name)


async def _precache_destruction_debris(debris_name: str, cache: Any) -> None:
    """Pre-cache the debris object blueprint so destruction feels instant."""
    if await cache.exists_creation(debris_name):
        return

    from app.creator.pipeline import create_object

    try:
        await create_object(debris_name, cache)
        logger.info("destruction_debris_precached", name=debris_name)
    except Exception:
        logger.warning("destruction_debris_precache_failed", name=debris_name, exc_info=True)


async def _generate_and_deliver_sprite(
    session_id: str,
    blueprint: GameObjectBlueprint,
) -> None:
    """Generate sprite and push via WebSocket."""
    from app.images.pipeline import generate_sprite

    object_id = blueprint.id
    logger.info("sprite_generation_start", session_id=session_id, object_id=object_id)
    try:
        result = await generate_sprite(blueprint)
        if result is None:
            await send_sprite_failed(session_id, object_id, "generation_failed")
            return
        await send_sprite_ready(session_id, object_id, result.sprite_url)
    except Exception as exc:
        logger.error("sprite_delivery_failed", object_id=object_id, error=str(exc))
        try:
            await send_sprite_failed(session_id, object_id, "generation_exception")
        except Exception:
            logger.error("sprite_failed_notify_error", object_id=object_id, exc_info=True)


async def _run_spawn_integration(
    session_id: str,
    blueprint: GameObjectBlueprint,
    manager: SessionManager,
    cache: Any,
    scenes: dict,
) -> None:
    """Run collision screening/eval + creature behavior for newly spawned object."""
    from app.cache.scene import BehaviorCache
    from app.engine.creature import evaluate_creature_behaviors
    from app.engine.pairwise import collision_spawn_integration

    scene = scenes.setdefault(session_id, BehaviorCache())

    # Load all session objects for context
    session = await manager.get_session(session_id)
    if session is None:
        return

    scene_objects = [obj.blueprint for obj in session.objects if obj.blueprint.id != blueprint.id]

    # Collision force rules (screening + eval)
    try:
        results = await collision_spawn_integration(blueprint, scene_objects, cache, scene)
        if results:
            from app.cache.store import normalize_name

            entries = []
            for target_name, rule in results.items():
                entry = rule.to_dict()
                a, b = sorted([normalize_name(blueprint.name), normalize_name(target_name)])
                entry["name_a"] = a
                entry["name_b"] = b
                entries.append(entry)
            await send_collision_ready(session_id, entries)
    except Exception:
        logger.error(
            "collision_integration_failed",
            session_id=session_id,
            object_name=blueprint.name,
            exc_info=True,
        )

    # Creature behavior
    try:
        scene_names = [o.name for o in scene_objects] + [blueprint.name]

        # Evaluate new creature against all existing objects
        if blueprint.autonomous:
            behaviors = await evaluate_creature_behaviors(
                blueprint, scene_objects, scene_names, scene
            )
            if behaviors:
                from app.ws.handler import _format_behaviors

                await send_behaviors_ready(
                    session_id, blueprint.name, _format_behaviors(blueprint.name, behaviors)
                )

        # Evaluate existing creatures against new object (parallel)
        async def _eval_creature(obj: GameObjectBlueprint) -> None:
            behaviors = await evaluate_creature_behaviors(obj, [blueprint], scene_names, scene)
            if behaviors:
                from app.ws.handler import _format_behaviors

                await send_behaviors_ready(
                    session_id, obj.name, _format_behaviors(obj.name, behaviors)
                )

        creature_tasks = [_eval_creature(obj) for obj in scene_objects if obj.autonomous]
        if creature_tasks:
            await asyncio.gather(*creature_tasks, return_exceptions=True)
    except Exception:
        logger.error(
            "creature_eval_failed",
            session_id=session_id,
            object_name=blueprint.name,
            exc_info=True,
        )
