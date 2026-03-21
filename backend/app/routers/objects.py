from __future__ import annotations

import asyncio
import base64
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.creator.agent import create_object
from app.images.pipeline import SIZE_MAP
from app.models.blueprint import VisualDescriptor
from app.models.tags import Tag
from app.sessions.manager import SessionManager

router = APIRouter(prefix="/api/sessions/{session_id}/objects", tags=["objects"])

_background_tasks: set[asyncio.Task[Any]] = set()


class CreateObjectRequest(BaseModel):
    description: str


@router.post("")
async def create_object_endpoint(
    session_id: str, body: CreateObjectRequest, request: Request
) -> dict:
    """Create a new game object from a text description.

    Returns the blueprint and placeholder immediately.
    Sprite generation happens async and is delivered via WebSocket.
    """
    db = request.app.state.db
    manager = SessionManager(db)

    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check budget
    budget_remaining = settings.session_budget_usd - session.budget_used
    if budget_remaining <= 0:
        raise HTTPException(status_code=402, detail="Session budget exceeded")

    # Create object via LLM
    blueprint = await create_object(body.description)

    # Track LLM cost (~$0.001 per call)
    llm_cost = 0.001
    new_total = await manager.track_cost(session_id, llm_cost)

    # Save to session
    await manager.save_object(session_id, blueprint)

    # Generate placeholder and kick off async sprite generation
    from app.images.pipeline import generate_placeholder

    placeholder_bytes = generate_placeholder(
        blueprint.visual_descriptor, blueprint.tags
    )
    placeholder_b64 = base64.b64encode(placeholder_bytes).decode()

    # Schedule async sprite generation (will deliver via WebSocket)
    rembg_session = request.app.state.rembg_session
    task = asyncio.create_task(
        _generate_and_deliver_sprite(
            request.app, session_id, blueprint.id,
            blueprint.visual_descriptor, blueprint.tags, rembg_session,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Track image cost async (~$0.04 per call)
    cost_task = asyncio.create_task(
        manager.track_cost(session_id, 0.04)
    )
    _background_tasks.add(cost_task)
    cost_task.add_done_callback(_background_tasks.discard)

    return {
        "blueprint": blueprint.model_dump(mode="json"),
        "placeholder_png_base64": placeholder_b64,
        "budget_remaining": settings.session_budget_usd - new_total,
    }


async def _generate_and_deliver_sprite(
    app: FastAPI,
    session_id: str,
    object_id: str,
    visual_descriptor: VisualDescriptor,
    tags: list[Tag],
    rembg_session: object,
) -> None:
    """Background task: generate sprite and push via WebSocket."""
    from app.images.pipeline import generate_sprite

    try:
        sprite_bytes = await generate_sprite(
            object_id, visual_descriptor, tags, rembg_session
        )
        if sprite_bytes is None:
            return

        sprite_b64 = base64.b64encode(sprite_bytes).decode()
        size = SIZE_MAP.get(visual_descriptor.size_category, 64)

        # Deliver via WebSocket if connected
        ws_connections: dict = getattr(app.state, "ws_connections", {})
        ws = ws_connections.get(session_id)
        if ws:
            await ws.send_json({
                "type": "sprite_ready",
                "object_id": object_id,
                "sprite_png_base64": sprite_b64,
                "width": size,
                "height": size,
            })
    except Exception:
        pass  # Sprite failure is non-fatal; placeholder remains
