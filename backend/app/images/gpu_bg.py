"""Background removal via local rembg Docker service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.bg_removal_url,
            timeout=settings.image_timeout_seconds,
        )
        logger.info("gpu_bg_http_client_created", base_url=settings.bg_removal_url)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def make_gpu_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via the rembg Docker service."""

    async def remove_bg(image_bytes: bytes) -> bytes:
        logger.debug("gpu_bg_removal_start", input_size=len(image_bytes))
        client = _get_http_client()
        resp = await asyncio.wait_for(
            client.post(
                "/remove",
                content=image_bytes,
                headers={"Content-Type": "image/png"},
            ),
            timeout=settings.image_timeout_seconds,
        )
        resp.raise_for_status()
        result = resp.content
        logger.debug("gpu_bg_removal_complete", output_size=len(result))
        return result

    return remove_bg
