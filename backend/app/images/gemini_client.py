from __future__ import annotations

import asyncio
import io
from typing import Any

import structlog
from PIL import Image

from app.config import settings

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)

# Lazy singleton; typed as Any because google-genai has no mypy stubs.
_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.google_api_key)
    return _client


def _ensure_png(data: bytes) -> bytes:
    """Convert to PNG if Gemini returned JPEG."""
    if data[:4] == b"\x89PNG":
        return data
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_image(prompt: str) -> bytes:
    """Generate an image via Gemini. Returns raw PNG bytes.

    Uses the native async API. Limits concurrency with a semaphore
    and enforces a timeout.
    """
    from google.genai import types

    logger.info("gemini_generate_start", prompt_len=len(prompt))
    client = _get_client()

    async with _semaphore:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=settings.image_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        image_size="1K",
                        aspect_ratio="1:1",
                    ),
                ),
            ),
            timeout=settings.image_timeout_seconds,
        )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        raise ValueError(f"Gemini image generation blocked: {reason}")

    for part in response.parts:
        if part.inline_data is not None:
            result = _ensure_png(part.inline_data.data)
            logger.info("gemini_generate_complete", size_bytes=len(result))
            return result

    raise ValueError("No image data in Gemini response")
