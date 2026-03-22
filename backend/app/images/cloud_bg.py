from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable

import structlog

from app.config import settings

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)


def make_cloud_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via fal.ai birefnet."""

    async def remove_bg(image_bytes: bytes) -> bytes:
        from app.images.fal_helpers import submit_and_download

        logger.debug("cloud_bg_request", size_bytes=len(image_bytes))
        t0 = time.monotonic()
        image_b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:image/png;base64,{image_b64}"

        async with _semaphore:
            result = await asyncio.wait_for(
                submit_and_download(
                    "fal-ai/birefnet",
                    arguments={
                        "image_url": data_uri,
                        "model": "General",
                        "operating_resolution": "1024x1024",
                    },
                    result_key="image",
                ),
                timeout=settings.image_timeout_seconds,
            )
        logger.debug("cloud_bg_response", elapsed=round(time.monotonic() - t0, 2))
        return result

    return remove_bg
