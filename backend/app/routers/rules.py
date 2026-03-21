from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Request, Response

from app.engine.rules_data import ALL_RULES

router = APIRouter(prefix="/api/rules", tags=["rules"])

# Pre-compute ETag for rules (they don't change at runtime)
_rules_json = [r.model_dump(mode="json") for r in ALL_RULES]
_rules_bytes = json.dumps(_rules_json, separators=(",", ":")).encode()
_rules_etag = f'"{hashlib.md5(_rules_bytes).hexdigest()}"'


@router.get("")
async def get_rules(request: Request) -> Response:
    """Download all interaction rules. Supports ETag caching."""
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == _rules_etag:
        return Response(status_code=304)

    return Response(
        content=_rules_bytes,
        media_type="application/json",
        headers={"ETag": _rules_etag},
    )
