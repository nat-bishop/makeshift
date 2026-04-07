from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.cache.manager import CacheManager
from app.sessions.manager import SessionManager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/pairwise", tags=["pairwise"])


@router.get("/scene/{session_id}")
async def get_scene_pairwise(session_id: str, request: Request) -> dict:
    """Bulk-fetch all cached pairwise results for objects in this session."""
    db = request.app.state.db
    cache_db = request.app.state.cache_db
    manager = SessionManager(db)
    cache = CacheManager(cache_db)
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    names = [obj.blueprint.name for obj in session.objects]
    results = await cache.get_all_for_names("pairwise", names)
    return {"pairs": results}
