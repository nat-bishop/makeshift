from __future__ import annotations

import asyncio

import structlog

from app.config import settings
from app.images.fal_helpers import fal_semaphore, submit_and_download

logger = structlog.get_logger()


async def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes:
    """Generate an image via fal.ai Flux Pro. Returns raw PNG bytes.

    Limits concurrency with a shared semaphore and enforces a timeout.
    """
    logger.info("flux_generate_start", prompt_len=len(prompt), width=width, height=height)
    async with fal_semaphore:
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
        logger.info("flux_generate_complete", size_bytes=len(result))
        return result
