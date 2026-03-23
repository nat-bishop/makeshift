from __future__ import annotations

import asyncio
import base64
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.creator.agent import create_object
from app.images.pipeline import RemoveBg
from app.models.blueprint import VisualDescriptor
from app.models.tags import SIZE_PIXEL_MAP, Tag
from app.sessions.manager import SessionManager
from app.ws.handler import send_sprite_failed, send_sprite_ready

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions/{session_id}/objects", tags=["objects"])

# Per-object creation cost charged upfront: LLM (~$0.001) + image (~$0.04)
OBJECT_CREATION_COST = 0.041

_background_tasks: set[asyncio.Task[Any]] = set()


class CreateObjectRequest(BaseModel):
    description: str


class CreateObjectResponse(BaseModel):
    blueprint: dict
    placeholder_png_base64: str
    budget_remaining: float


@router.post("", response_model=CreateObjectResponse)
async def create_object_endpoint(
    session_id: str, body: CreateObjectRequest, request: Request
) -> CreateObjectResponse:
    """Create a new game object from a text description.

    Returns the blueprint and placeholder immediately.
    Sprite generation happens async and is delivered via WebSocket.
    """
    db = request.app.state.db
    manager = SessionManager(db)

    budget_info = await manager.get_budget_info(session_id)
    if budget_info is None:
        logger.warning("object_create_session_not_found")
        raise HTTPException(status_code=404, detail="Session not found")

    budget_remaining, budget_limit = budget_info
    if budget_remaining <= 0:
        logger.warning("object_create_budget_exceeded", budget_remaining=budget_remaining)
        raise HTTPException(status_code=402, detail="Session budget exceeded")

    logger.info("object_create_request", description_len=len(body.description))

    # Create object via LLM
    blueprint = await create_object(body.description)

    # Track cost and save object in one transaction
    new_total = await manager.track_cost_and_save_object(
        session_id, OBJECT_CREATION_COST, blueprint
    )

    # Generate placeholder and kick off async sprite generation
    from app.images.pipeline import generate_placeholder

    placeholder_bytes = generate_placeholder(blueprint.visual_descriptor, blueprint.tags)
    placeholder_b64 = base64.b64encode(placeholder_bytes).decode()

    # Schedule async sprite generation (will deliver via WebSocket)
    remove_bg = request.app.state.remove_bg
    task = asyncio.create_task(
        _generate_and_deliver_sprite(
            session_id,
            blueprint.id,
            blueprint.visual_descriptor,
            blueprint.tags,
            remove_bg,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return CreateObjectResponse(
        blueprint=blueprint.model_dump(mode="json"),
        placeholder_png_base64=placeholder_b64,
        budget_remaining=budget_limit - new_total,
    )


async def _generate_and_deliver_sprite(
    session_id: str,
    object_id: str,
    visual_descriptor: VisualDescriptor,
    tags: list[Tag],
    remove_bg: RemoveBg,
) -> None:
    """Background task: generate sprite and push via WebSocket."""
    from app.images.pipeline import generate_sprite

    try:
        sprite_bytes = await generate_sprite(object_id, visual_descriptor, tags, remove_bg)
        if sprite_bytes is None:
            logger.warning("sprite_generation_returned_none", object_id=object_id)
            await send_sprite_failed(session_id, object_id, "generation_failed")
            return

        size = SIZE_PIXEL_MAP[visual_descriptor.size_category]
        await send_sprite_ready(session_id, object_id, sprite_bytes, size, size)
    except Exception:
        logger.error(
            "sprite_delivery_failed",
            object_id=object_id,
            exc_info=True,
        )
        try:
            await send_sprite_failed(session_id, object_id, "generation_exception")
        except Exception:
            logger.error("sprite_failed_notify_error", object_id=object_id, exc_info=True)
