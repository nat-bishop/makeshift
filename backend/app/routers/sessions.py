from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.engine.rules_data import ALL_RULES
from app.models.session import EquipmentSlot, InventorySlot, WorldObject
from app.seed.objects import SEED_OBJECTS
from app.sessions.manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_RULES_JSON = [r.model_dump(mode="json") for r in ALL_RULES]


@router.post("")
async def create_session(request: Request) -> dict:
    """Create a new game session. Returns session data, seed objects, rules, and ws_url."""
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.create_session()

    # Seed objects into the session
    seed_blueprints = []
    for bp in SEED_OBJECTS:
        await manager.save_object(session.id, bp)
        seed_blueprints.append(bp.model_dump(mode="json"))

    rules_json = _RULES_JSON

    host = request.headers.get("host", f"{settings.host}:{settings.port}")
    ws_url = f"ws://{host}/ws/{session.id}"

    return {
        "session_id": session.id,
        "created_at": session.created_at,
        "budget_remaining": settings.session_budget_usd - session.budget_used,
        "seed_objects": seed_blueprints,
        "rules": rules_json,
        "ws_url": ws_url,
    }


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    """Restore an existing session."""
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    rules_json = _RULES_JSON
    host = request.headers.get("host", f"{settings.host}:{settings.port}")
    ws_url = f"ws://{host}/ws/{session.id}"

    return {
        "session": session.model_dump(mode="json"),
        "rules": rules_json,
        "ws_url": ws_url,
        "budget_remaining": settings.session_budget_usd - session.budget_used,
    }


class SyncRequest(BaseModel):
    objects: list[WorldObject]
    inventory: list[InventorySlot]
    equipment: list[EquipmentSlot]
    level_progress: int


@router.put("/{session_id}/sync")
async def sync_session(session_id: str, body: SyncRequest, request: Request) -> dict:
    """Batch state sync from client."""
    db = request.app.state.db
    manager = SessionManager(db)

    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await manager.save_state(
        session_id,
        body.objects,
        body.inventory,
        body.equipment,
        body.level_progress,
    )
    return {"status": "ok"}
