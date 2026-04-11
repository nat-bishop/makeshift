"""Collision rule query endpoint — lazy evaluation fallback.

Called by the Godot client on collision cache miss (via WS or HTTP).
Evaluates the pair's force rule via LLM and returns the result.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.cache.scene import BehaviorCache, no_force
from app.engine.pairwise import evaluate_collision
from app.sessions.manager import SessionManager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions/{session_id}/interactions", tags=["interactions"])


class CollisionRequest(BaseModel):
    name_a: str
    name_b: str


class CollisionResponse(BaseModel):
    force_on_b: int  # signed: negative=pull, positive=push
    cached: bool


@router.get("/scene")
async def get_scene_collisions(session_id: str, request: Request) -> dict:
    """Bulk-load all cached collision entries for all objects in a session."""
    logger.debug("scene_collision_request", session_id=session_id)
    cache = request.app.state.cache
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        return {"pairs": {}}

    names = [obj.blueprint.name for obj in session.objects]
    pairs = await cache.get_all_collisions_for_names(names)
    logger.debug("scene_collision_loaded", pair_count=len(pairs))
    return {"pairs": pairs}


@router.post("", response_model=CollisionResponse)
async def query_collision(
    session_id: str, body: CollisionRequest, request: Request
) -> CollisionResponse:
    """Evaluate a collision force rule on demand (cache miss fallback)."""
    logger.debug("query_collision_request", name_a=body.name_a, name_b=body.name_b)
    cache = request.app.state.cache

    scenes: dict = request.app.state.scenes
    scene = scenes.get(session_id)
    if scene is None:
        logger.warning("query_collision_no_scene", session_id=session_id)
        scenes[session_id] = BehaviorCache()
        scene = scenes[session_id]

    # Look up blueprints for prompt context
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        logger.warning("query_collision_no_session", session_id=session_id)
        return CollisionResponse(**no_force().to_dict(), cached=False)

    bp_a = None
    bp_b = None
    for obj in session.objects:
        if obj.blueprint.name.lower() == body.name_a.lower():
            bp_a = obj.blueprint
        if obj.blueprint.name.lower() == body.name_b.lower():
            bp_b = obj.blueprint

    if bp_a is None or bp_b is None:
        return CollisionResponse(**no_force().to_dict(), cached=False)

    result = await evaluate_collision(bp_a, bp_b, cache, scene)
    logger.info("query_collision_complete", name_a=body.name_a, name_b=body.name_b)
    return CollisionResponse(**result.to_dict(), cached=True)
