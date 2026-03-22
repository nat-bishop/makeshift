from __future__ import annotations

import asyncio

from app.config import settings
from app.images.fal_helpers import fal_semaphore, submit_and_download


async def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes:
    """Generate an image via fal.ai Flux Kontext. Returns raw PNG bytes.

    Limits concurrency with a shared semaphore and enforces a timeout.
    """
    async with fal_semaphore:
        return await asyncio.wait_for(
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
