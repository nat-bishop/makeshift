"""Cloud FLUX image generation via fal.ai."""

from __future__ import annotations

import asyncio

import structlog

from app.config import settings
from app.images.fal_helpers import fal_semaphore, submit_and_download

logger = structlog.get_logger()


async def generate_image(prompt: str) -> bytes:
    """Generate an image via fal.ai FLUX. Returns raw PNG bytes."""
    logger.info("fal_image_generate_start", prompt_len=len(prompt))
    async with fal_semaphore:
        result = await asyncio.wait_for(
            submit_and_download(
                settings.fal_image_model,
                arguments={
                    "prompt": prompt,
                    "num_images": 1,
                    "image_size": {"width": 512, "height": 512},
                },
                result_key="images",
            ),
            timeout=settings.image_timeout_seconds,
        )
    logger.info("fal_image_generate_complete", size_bytes=len(result))
    return result
