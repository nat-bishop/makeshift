"""GPU-accelerated background removal using rembg with BiRefNet."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger()

_session: Any = None
_load_lock = threading.Lock()

# Serialize GPU inference — one call saturates the GPU; concurrent calls risk OOM.
_inference_semaphore: asyncio.Semaphore | None = None


def _get_session() -> Any:
    global _session
    if _session is not None:
        return _session

    with _load_lock:
        if _session is not None:
            return _session

        from rembg import new_session

        logger.info("bg_model_loading", model="birefnet-general")
        _session = new_session("birefnet-general")
        logger.info("bg_model_loaded", model="birefnet-general")
        return _session


def _remove_bg_sync(image_bytes: bytes) -> bytes:
    """Run rembg background removal synchronously. Call from a thread."""
    from rembg import remove

    session = _get_session()
    result: bytes = remove(image_bytes, session=session)
    return result


def make_gpu_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via rembg on GPU."""
    global _inference_semaphore
    _inference_semaphore = asyncio.Semaphore(1)

    async def remove_bg(image_bytes: bytes) -> bytes:
        assert _inference_semaphore is not None
        logger.debug("gpu_bg_removal_start", input_size=len(image_bytes))
        async with _inference_semaphore:
            result = await asyncio.to_thread(_remove_bg_sync, image_bytes)
        logger.debug("gpu_bg_removal_complete", output_size=len(result))
        return result

    return remove_bg
