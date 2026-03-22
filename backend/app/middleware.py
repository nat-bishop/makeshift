from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

_SESSION_RE = re.compile(r"(?:/api/sessions/|/ws/)([^/]+)")


async def session_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bind session_id from the URL path into structlog contextvars."""
    match = _SESSION_RE.search(request.url.path)
    if match:
        structlog.contextvars.bind_contextvars(session_id=match.group(1))
    try:
        return await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
