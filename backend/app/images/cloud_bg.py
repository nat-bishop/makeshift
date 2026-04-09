from __future__ import annotations

import asyncio
import base64
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.images.fal_helpers import fal_semaphore, submit_and_download

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()


def make_cloud_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via fal.ai birefnet."""

    async def remove_bg(image_bytes: bytes) -> bytes:
        logger.info("cloud_bg_removal_start", input_size=len(image_bytes))
        image_b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:image/png;base64,{image_b64}"

        try:
            async with fal_semaphore:
                result = await asyncio.wait_for(
                    submit_and_download(
                        "fal-ai/birefnet",
                        arguments={
                            "image_url": data_uri,
                            "model": "General Use (Light)",
                            "operating_resolution": "1024x1024",
                        },
                        result_key="image",
                    ),
                    timeout=settings.image_timeout_seconds,
                )
                logger.info("cloud_bg_removal_complete", output_size=len(result))
                return result
        except Exception:
            logger.error(
                "cloud_bg_removal_failed",
                input_size=len(image_bytes),
                exc_info=True,
            )
            raise

    return remove_bg
