"""Object creation endpoint — V3 pipeline with unified behavior integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.sessions.manager import SessionManager
from app.ws.handler import (
    send_behaviors_ready,
    send_combined_sprite_ready,
    send_destruction_sprite_ready,
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
    Sprite generation + behavior integration happen async via background tasks.
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

    # Schedule background tasks: sprite gen + behavior integration + img2img follow-ups
    scenes = request.app.state.scenes
    task = asyncio.create_task(_background_spawn(session_id, blueprint, manager, cache, scenes))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Pre-cache destruction debris BLUEPRINT (metadata only) in background.
    # The debris SPRITE is generated separately inside _background_spawn via img2img.
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
    """Background: sprite gen + behavior eval in parallel, then img2img follow-ups.

    Phase 1 (parallel): base sprite generation + behavior screening/eval.
    Phase 2 (parallel, only if sprite bytes available): carry/ride and destruction
    img2img sprites. Both depend on the base sprite bytes.
    """
    logger.info("background_spawn_start", name=blueprint.name)

    # Phase 1: sprite gen and behavior eval can run in parallel
    sprite_result, behavior_result = await asyncio.gather(
        _generate_and_deliver_sprite(session_id, blueprint),
        _run_spawn_integration(session_id, blueprint, manager, cache, scenes),
        return_exceptions=True,
    )

    if isinstance(behavior_result, BaseException):
        logger.error(
            "behavior_integration_failed",
            name=blueprint.name,
            error=str(behavior_result),
        )

    # Phase 2: img2img follow-ups (need the base sprite bytes)
    sprite_bytes: bytes | None
    if isinstance(sprite_result, BaseException):
        logger.error(
            "sprite_generation_failed",
            name=blueprint.name,
            error=str(sprite_result),
        )
        sprite_bytes = None
    else:
        sprite_bytes = sprite_result

    if sprite_bytes is None:
        logger.info("background_spawn_complete_no_sprite", name=blueprint.name)
        return

    img2img_tasks: list[Any] = []
    if blueprint.affordance in (0, 1):
        img2img_tasks.append(_precache_combined_sprite(session_id, blueprint, sprite_bytes))
    if blueprint.destruction_result_name:
        img2img_tasks.append(_precache_destruction_sprite(session_id, blueprint, sprite_bytes))

    if img2img_tasks:
        img2img_results = await asyncio.gather(*img2img_tasks, return_exceptions=True)
        errors = [r for r in img2img_results if isinstance(r, BaseException)]
        if errors:
            logger.error("img2img_tasks_failed", name=blueprint.name, errors=errors)

    logger.info("background_spawn_complete", name=blueprint.name)


async def _precache_destruction_debris(debris_name: str, cache: Any) -> None:
    """Pre-cache the debris object blueprint so destruction feels instant.

    This only creates the blueprint metadata -- the destruction SPRITE is
    generated separately from the source object's sprite via img2img.
    """
    if await cache.exists_creation(debris_name):
        return

    from app.creator.pipeline import create_object

    try:
        await create_object(debris_name, cache)
        logger.info("destruction_debris_precached", name=debris_name)
    except Exception:
        logger.warning("destruction_debris_precache_failed", name=debris_name, exc_info=True)


async def _precache_combined_sprite(
    session_id: str,
    blueprint: GameObjectBlueprint,
    object_sprite_bytes: bytes,
) -> None:
    """Generate the carry/ride combined sprite via FLUX img2img and deliver it."""
    from app.images.pipeline import STATIC_DIR, generate_carry_ride_sprite

    cache_path = STATIC_DIR / "sprites" / f"combined_{blueprint.id}.png"
    sprite_url = f"/static/sprites/{cache_path.name}"

    if cache_path.exists():
        await send_combined_sprite_ready(session_id, blueprint.id, sprite_url)
        return

    try:
        final_bytes = await generate_carry_ride_sprite(
            blueprint.affordance,
            blueprint.name,
            blueprint.visual_description,
            object_sprite_bytes,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(final_bytes)
        logger.info("combined_sprite_precached", name=blueprint.name, path=str(cache_path))
    except Exception:
        logger.warning("combined_sprite_precache_failed", name=blueprint.name, exc_info=True)
        return

    await send_combined_sprite_ready(session_id, blueprint.id, sprite_url)


async def _precache_destruction_sprite(
    session_id: str,
    blueprint: GameObjectBlueprint,
    object_sprite_bytes: bytes,
) -> None:
    """Generate a debris sprite via FLUX img2img from the source object's sprite."""
    from app.images.pipeline import STATIC_DIR, generate_destruction_sprite

    debris_name = blueprint.destruction_result_name
    if not debris_name:
        return

    cache_path = STATIC_DIR / "sprites" / f"destruction_{blueprint.id}.png"
    sprite_url = f"/static/sprites/{cache_path.name}"

    if cache_path.exists():
        await send_destruction_sprite_ready(session_id, blueprint.id, debris_name, sprite_url)
        return

    try:
        final_bytes = await generate_destruction_sprite(
            blueprint.name,
            blueprint.visual_description,
            debris_name,
            object_sprite_bytes,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(final_bytes)
        logger.info(
            "destruction_sprite_precached",
            name=blueprint.name,
            debris=debris_name,
            path=str(cache_path),
        )
    except Exception:
        logger.warning(
            "destruction_sprite_precache_failed",
            name=blueprint.name,
            exc_info=True,
        )
        return

    await send_destruction_sprite_ready(session_id, blueprint.id, debris_name, sprite_url)


async def _generate_and_deliver_sprite(
    session_id: str,
    blueprint: GameObjectBlueprint,
) -> bytes | None:
    """Generate sprite, push via WebSocket, and return the sprite bytes for img2img."""
    from app.images.pipeline import generate_sprite

    object_id = blueprint.id
    logger.info("sprite_generation_start", session_id=session_id, object_id=object_id)
    try:
        result = await generate_sprite(blueprint)
        if result is None:
            await send_sprite_failed(session_id, object_id, "generation_failed")
            return None
        await send_sprite_ready(session_id, object_id, result.sprite_url)
        return result.sprite_bytes
    except Exception as exc:
        logger.error("sprite_delivery_failed", object_id=object_id, error=str(exc))
        try:
            await send_sprite_failed(session_id, object_id, "generation_exception")
        except Exception:
            logger.error("sprite_failed_notify_error", object_id=object_id, exc_info=True)
        return None


async def _run_spawn_integration(
    session_id: str,
    blueprint: GameObjectBlueprint,
    manager: SessionManager,
    cache: Any,
    scenes: dict,
) -> None:
    """Run bidirectional screening + behavior evaluation for newly spawned object."""
    from app.cache.scene import BehaviorCache
    from app.engine.behavior import evaluate_behaviors, screen_pairs
    from app.ws.handler import format_behaviors

    scene = scenes.setdefault(session_id, BehaviorCache())

    # Load all session objects for context
    session = await manager.get_session(session_id)
    if session is None:
        return

    from app.models.blueprint import PLAYER_BLUEPRINT

    scene_objects = [obj.blueprint for obj in session.objects if obj.blueprint.id != blueprint.id]
    scene_objects.append(PLAYER_BLUEPRINT)  # always include player as potential target

    # Bidirectional screen: which pairs are interesting?
    interesting = await screen_pairs(blueprint, scene_objects)
    if not interesting:
        logger.info(
            "spawn_screen_empty",
            session_id=session_id,
            object_name=blueprint.name,
            scene_size=len(scene_objects),
        )
        return

    bp_by_name = {o.name: o for o in scene_objects}
    interesting_bps = [bp_by_name[n] for n in interesting if n in bp_by_name]

    # Evaluate both directions for each interesting pair
    async def _eval_direction(
        subject: GameObjectBlueprint, targets: list[GameObjectBlueprint]
    ) -> None:
        behaviors = await evaluate_behaviors(subject, targets, scene)
        if behaviors:
            entries = format_behaviors(subject.name, behaviors)
            await send_behaviors_ready(session_id, subject.name, entries)
        else:
            logger.warning(
                "empty_behaviors_dict",
                subject=subject.name,
                target_count=len(targets),
            )

    tasks = []

    # New object → interesting scene objects
    tasks.append(_eval_direction(blueprint, interesting_bps))

    # Reverse direction: only evaluate when the scene-object subject can actually
    # act on the result. Passive props never tick ObjectBehavior, and the
    # Player is user-controlled even though PLAYER_BLUEPRINT.active is True.
    def _can_act(bp: GameObjectBlueprint) -> bool:
        return bp.active and bp.id != "player"

    skipped = [bp.name for bp in interesting_bps if not _can_act(bp)]
    if skipped:
        logger.info(
            "reverse_eval_skipped",
            session_id=session_id,
            new_object=blueprint.name,
            skipped_subjects=skipped,
        )
    tasks.extend(
        _eval_direction(target_bp, [blueprint])
        for target_bp in interesting_bps
        if _can_act(target_bp)
    )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            logger.error(
                "behavior_integration_failed",
                session_id=session_id,
                object_name=blueprint.name,
                error=str(result),
            )
