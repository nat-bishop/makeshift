"""Local FLUX image generation via SGLang server."""

from __future__ import annotations

import asyncio
import base64

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.local_image_url,
            timeout=settings.image_timeout_seconds,
        )
        logger.info("local_image_http_client_created", base_url=settings.local_image_url)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def generate_image(prompt: str) -> bytes:
    """Generate an image via local SGLang FLUX server. Returns raw PNG bytes."""
    logger.info("local_generate_start", prompt_len=len(prompt))
    client = _get_http_client()
    resp = await asyncio.wait_for(
        client.post(
            "/v1/images/generations",
            json={
                "model": settings.local_image_model,
                "prompt": prompt,
                "n": 1,
                "size": "512x512",
                "response_format": "b64_json",
            },
        ),
        timeout=settings.image_timeout_seconds,
    )
    resp.raise_for_status()
    b64_data = resp.json()["data"][0]["b64_json"]
    result = base64.b64decode(b64_data)
    logger.info("local_generate_complete", size_bytes=len(result))
    return result
