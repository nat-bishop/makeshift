
import asyncio
import base64
from collections.abc import Awaitable, Callable

from app.config import settings

_semaphore = asyncio.Semaphore(settings.max_concurrent_image_requests)


def make_cloud_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via fal.ai birefnet."""

    async def remove_bg(image_bytes: bytes) -> bytes:
        from app.images.fal_helpers import submit_and_download

        image_b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:image/png;base64,{image_b64}"

        async with _semaphore:
            return await asyncio.wait_for(
                submit_and_download(
                    "fal-ai/birefnet",
                    arguments={
                        "image_url": data_uri,
                        "model": "General",
                        "operating_resolution": "1024x1024",
                    },
                    result_key="image",
                ),
                timeout=settings.image_timeout_seconds,
            )

    return remove_bg
