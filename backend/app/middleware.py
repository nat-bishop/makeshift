from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

_SESSION_RE = re.compile(r"(?:/api/sessions/|/ws/)([^/]+)")


logger = structlog.get_logger()


async def session_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bind session_id from the URL path into structlog contextvars."""
    match = _SESSION_RE.search(request.url.path)
    if match:
        structlog.contextvars.bind_contextvars(session_id=match.group(1))
    try:
        start = time.monotonic()
        response = await call_next(request)
        elapsed = round(time.monotonic() - start, 2)
        logger.debug(
            "request_completed",
            path=request.url.path,
            method=request.method,
            elapsed=elapsed,
            status=response.status_code,
        )
        if elapsed > 1.0:
            logger.warning(
                "slow_request",
                path=request.url.path,
                method=request.method,
                elapsed=elapsed,
                status=response.status_code,
            )
        return response
    finally:
        structlog.contextvars.clear_contextvars()
