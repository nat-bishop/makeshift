from __future__ import annotations

import asyncio

from app.config import settings

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)


async def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes:
    """Generate an image via fal.ai Flux Kontext. Returns raw PNG bytes.

    Limits concurrency with a semaphore and enforces a timeout.
    """
    from app.images.fal_helpers import submit_and_download

    async with _semaphore:
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
