from __future__ import annotations

import asyncio

import fal_client

from app.config import settings

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)


async def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes:
    """Generate an image via fal.ai Flux Kontext. Returns raw PNG bytes.

    Limits concurrency with a semaphore and enforces a timeout.
    """
    async with _semaphore:
        result = await asyncio.wait_for(
            _submit_flux(prompt, width, height),
            timeout=settings.image_timeout_seconds,
        )
        return result


async def _submit_flux(prompt: str, width: int, height: int) -> bytes:
    """Submit to fal.ai and download the result image."""
    import httpx

    handler = await fal_client.submit_async(
        "fal-ai/flux-pro/kontext",
        arguments={
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_images": 1,
        },
    )
    result = await handler.get()
    if not result.get("images"):
        raise ValueError("No images in fal.ai response")
    image_url = result["images"][0]["url"]

    async with httpx.AsyncClient() as client:
        response = await client.get(image_url)
        response.raise_for_status()
        return response.content
