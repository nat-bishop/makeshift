from __future__ import annotations

import asyncio
from typing import Any

import fal_client
import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

fal_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def submit_and_download(
    endpoint: str,
    arguments: dict[str, Any],
    result_key: str = "images",
) -> bytes:
    """Submit a job to fal.ai and download the resulting image.

    Args:
        endpoint: The fal.ai model endpoint (e.g. "fal-ai/flux-pro/v1.1").
        arguments: Arguments to pass to the model.
        result_key: Top-level key in the response containing image data.
            "images" for endpoints returning a list, "image" for single-image endpoints.

    Returns:
        Raw image bytes.
    """
    logger.info("fal_submit", endpoint=endpoint)
    handler = await fal_client.submit_async(endpoint, arguments=arguments)
    result = await handler.get()
    logger.debug("fal_result_received", endpoint=endpoint, result_key=result_key)

    if result_key == "image":
        image_data = result.get("image")
        if not image_data:
            logger.error("fal_no_image_in_response", endpoint=endpoint, result_key=result_key)
            raise ValueError(f"No '{result_key}' in fal.ai response")
        image_url: str = image_data["url"]
    else:
        images = result.get("images")
        if not images:
            logger.error("fal_no_image_in_response", endpoint=endpoint, result_key=result_key)
            raise ValueError(f"No '{result_key}' in fal.ai response")
        image_url = images[0]["url"]

    client = _get_http_client()
    resp = await client.get(image_url)
    resp.raise_for_status()
    logger.info("fal_download_complete", endpoint=endpoint, size_bytes=len(resp.content))
    return resp.content
