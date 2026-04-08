"""Pairwise interaction query endpoint — lazy evaluation fallback.

Called by the Godot client on collision cache miss.
Evaluates the pair via LLM and returns the result synchronously.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.cache.scene import nothing_happens
from app.engine.pairwise import evaluate_pair
from app.sessions.manager import SessionManager

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/sessions/{session_id}/interactions", tags=["interactions"]
)


class InteractionRequest(BaseModel):
    name_a: str
    name_b: str


class InteractionResponse(BaseModel):
    damage_a: int  # 0-100, 100=destroyed
    damage_b: int  # 0-100, 100=destroyed
    state_change_a: int  # 0=none, 1-4=add, 5-8=remove
    state_change_b: int
    force_b: int  # -100 to 100 (negative=pull)
    continuous: bool
    cached: bool


@router.get("/scene")
async def get_scene_pairwise(
    session_id: str, request: Request
) -> dict:
    """Bulk-load all cached pairwise entries for all objects in a session."""
    cache = request.app.state.cache
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        return {"pairs": {}}

    names = [obj.blueprint.name for obj in session.objects]
    pairs = await cache.get_all_for_names("pairwise", names)
    return {"pairs": pairs}


@router.post("", response_model=InteractionResponse)
async def query_interaction(
    session_id: str, body: InteractionRequest, request: Request
) -> InteractionResponse:
    """Evaluate a pairwise interaction on demand (cache miss fallback)."""
    cache = request.app.state.cache

    scenes: dict = request.app.state.scenes
    scene = scenes.get(session_id)
    if scene is None:
        nh = nothing_happens()
        return InteractionResponse(**nh.to_dict(), cached=False)

    # Look up blueprints for prompt context
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        nh = nothing_happens()
        return InteractionResponse(**nh.to_dict(), cached=False)

    bp_a = None
    bp_b = None
    for obj in session.objects:
        if obj.blueprint.name.lower() == body.name_a.lower():
            bp_a = obj.blueprint
        if obj.blueprint.name.lower() == body.name_b.lower():
            bp_b = obj.blueprint

    if bp_a is None or bp_b is None:
        nh = nothing_happens()
        return InteractionResponse(**nh.to_dict(), cached=False)

    result = await evaluate_pair(bp_a, bp_b, cache, scene)
    return InteractionResponse(**result.to_dict(), cached=True)
