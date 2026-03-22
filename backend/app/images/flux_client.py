from __future__ import annotations

import asyncio
import time

import structlog

from app.config import settings

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)


async def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes:
    """Generate an image via fal.ai Flux Kontext. Returns raw PNG bytes.

    Limits concurrency with a semaphore and enforces a timeout.
    """
    from app.images.fal_helpers import submit_and_download

    logger.debug("flux_request", width=width, height=height, prompt_len=len(prompt))
    t0 = time.monotonic()
    async with _semaphore:
        result = await asyncio.wait_for(
            submit_and_download(
                settings.image_model,
                arguments={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_images": 1,
                },
            ),
            timeout=settings.image_timeout_seconds,
        )
    logger.debug(
        "flux_response", size_bytes=len(result), elapsed=round(time.monotonic() - t0, 2)
    )
    return result
