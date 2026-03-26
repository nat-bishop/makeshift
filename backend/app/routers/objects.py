from __future__ import annotations

import asyncio
import base64
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.creator.agent import create_object
from app.images.pipeline import RemoveBg
from app.models.blueprint import VisualDescriptor
from app.sessions.manager import SessionManager
from app.ws.handler import send_sprite_failed, send_sprite_ready

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions/{session_id}/objects", tags=["objects"])

# Per-object creation cost charged upfront: LLM (~$0.001) + image (~$0.04)
OBJECT_CREATION_COST = 0.041

_background_tasks: set[asyncio.Task[Any]] = set()


class CreateObjectRequest(BaseModel):
    description: str = Field(max_length=500)


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

    # Atomically reserve budget before calling the LLM
    success, budget_remaining = await manager.reserve_budget(session_id, OBJECT_CREATION_COST)
    if not success:
        if budget_remaining < 0:
            logger.warning("object_create_session_not_found")
            raise HTTPException(status_code=404, detail="Session not found")
        logger.warning("object_create_budget_exceeded", budget_remaining=budget_remaining)
        raise HTTPException(status_code=402, detail="Session budget exceeded")

    logger.info("object_create_request", description_len=len(body.description))

    # Create object via LLM (budget already reserved)
    blueprint = await create_object(body.description)

    # Save object
    await manager.save_object(session_id, blueprint)
    logger.debug("object_saved", session_id=session_id, object_id=blueprint.id)

    # Generate placeholder and kick off async sprite generation
    from app.images.pipeline import generate_placeholder

    placeholder_bytes = generate_placeholder(blueprint.visual_descriptor, blueprint.tags)
    placeholder_b64 = base64.b64encode(placeholder_bytes).decode()
    logger.debug("placeholder_generated", object_id=blueprint.id, size_bytes=len(placeholder_bytes))

    # Schedule async sprite generation (will deliver via WebSocket)
    remove_bg = request.app.state.remove_bg
    task = asyncio.create_task(
        _generate_and_deliver_sprite(
            session_id,
            blueprint.id,
            blueprint.visual_descriptor,
            remove_bg,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.debug("sprite_task_created", session_id=session_id, object_id=blueprint.id)

    return CreateObjectResponse(
        blueprint=blueprint.model_dump(mode="json"),
        placeholder_png_base64=placeholder_b64,
        budget_remaining=budget_remaining,
    )


async def _generate_and_deliver_sprite(
    session_id: str,
    object_id: str,
    visual_descriptor: VisualDescriptor,
    remove_bg: RemoveBg,
) -> None:
    """Background task: generate sprite and push via WebSocket."""
    from app.images.pipeline import generate_sprite

    logger.info("sprite_generation_start", session_id=session_id, object_id=object_id)
    try:
        result = await generate_sprite(
            object_id, visual_descriptor, remove_bg
        )
        if result is None:
            logger.warning("sprite_generation_returned_none", object_id=object_id)
            await send_sprite_failed(session_id, object_id, "generation_failed")
            return

        await send_sprite_ready(session_id, object_id, result.sprite_url)
        logger.info(
            "sprite_delivery_success",
            session_id=session_id,
            object_id=object_id,
            sprite_url=result.sprite_url,
        )
    except Exception as exc:
        logger.error(
            "sprite_delivery_failed",
            object_id=object_id,
            error=str(exc),
        )
        try:
            await send_sprite_failed(session_id, object_id, "generation_exception")
        except Exception:
            logger.error("sprite_failed_notify_error", object_id=object_id, exc_info=True)
