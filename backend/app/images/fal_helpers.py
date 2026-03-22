from __future__ import annotations

from typing import Any

import fal_client
import httpx
import structlog

logger = structlog.get_logger()

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
        endpoint: The fal.ai model endpoint (e.g. "fal-ai/flux-pro/kontext").
        arguments: Arguments to pass to the model.
        result_key: Top-level key in the response containing image data.
            "images" for endpoints returning a list, "image" for single-image endpoints.

    Returns:
        Raw image bytes.
    """
    logger.debug("fal_submit", endpoint=endpoint)
    handler = await fal_client.submit_async(endpoint, arguments=arguments)
    result = await handler.get()

    if result_key == "image":
        image_data = result.get("image")
        if not image_data:
            raise ValueError(f"No '{result_key}' in fal.ai response")
        image_url: str = image_data["url"]
    else:
        images = result.get("images")
        if not images:
            raise ValueError(f"No '{result_key}' in fal.ai response")
        image_url = images[0]["url"]

    client = _get_http_client()
    resp = await client.get(image_url)
    resp.raise_for_status()
    logger.debug("fal_download", size_bytes=len(resp.content))
    return resp.content
