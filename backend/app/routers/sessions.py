
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.engine.rules_data import ALL_RULES
from app.models.session import EquipmentSlots, InventorySlot, WorldObject
from app.seed.objects import SEED_OBJECTS
from app.sessions.manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_RULES_JSON = [r.model_dump(mode="json") for r in ALL_RULES]


class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    budget_remaining: float
    seed_objects: list[dict]
    rules: list[dict]
    ws_url: str


class GetSessionResponse(BaseModel):
    session: dict
    rules: list[dict]
    ws_url: str
    budget_remaining: float


class SyncRequest(BaseModel):
    objects: list[WorldObject] | None = None
    inventory: list[InventorySlot] | None = None
    equipment: EquipmentSlots | None = None
    current_level: int | None = None
    levels_completed: list[int] | None = None


@router.post("", response_model=CreateSessionResponse)
async def create_session(request: Request) -> CreateSessionResponse:
    """Create a new game session. Returns session data, seed objects, rules, and ws_url."""
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.create_session()

    # Seed objects into the session
    seed_blueprints = []
    for bp in SEED_OBJECTS:
        await manager.save_object(session.id, bp)
        seed_blueprints.append(bp.model_dump(mode="json"))

    host = request.headers.get("host", f"{settings.host}:{settings.port}")
    ws_url = f"ws://{host}/ws/{session.id}"

    return CreateSessionResponse(
        session_id=session.id,
        created_at=session.created_at,
        budget_remaining=session.budget_remaining,
        seed_objects=seed_blueprints,
        rules=_RULES_JSON,
        ws_url=ws_url,
    )


@router.get("/{session_id}", response_model=GetSessionResponse)
async def get_session(session_id: str, request: Request) -> GetSessionResponse:
    """Restore an existing session."""
    db = request.app.state.db
    manager = SessionManager(db)
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    host = request.headers.get("host", f"{settings.host}:{settings.port}")
    ws_url = f"ws://{host}/ws/{session.id}"

    return GetSessionResponse(
        session=session.model_dump(mode="json"),
        rules=_RULES_JSON,
        ws_url=ws_url,
        budget_remaining=session.budget_remaining,
    )


@router.put("/{session_id}/sync")
async def sync_session(session_id: str, body: SyncRequest, request: Request) -> dict:
    """Batch state sync from client. Only provided fields are updated."""
    db = request.app.state.db
    manager = SessionManager(db)

    if not await manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    await manager.save_state(
        session_id,
        objects=body.objects,
        inventory=body.inventory,
        equipment=body.equipment,
        current_level=body.current_level,
        levels_completed=body.levels_completed,
    )
    return {"status": "ok"}
