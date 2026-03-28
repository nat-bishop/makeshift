"""Background removal HTTP service wrapping rembg + BiRefNet."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("rembg-server")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

app = FastAPI(title="rembg", version="0.1.0")

_session: Any = None
_load_lock = threading.Lock()
_inference_semaphore = asyncio.Semaphore(1)


def _get_session() -> Any:
    global _session
    if _session is not None:
        return _session

    with _load_lock:
        if _session is not None:
            return _session

        from rembg import new_session

        logger.info("Loading BiRefNet model...")
        _session = new_session("birefnet-general")
        logger.info("BiRefNet model loaded")
        return _session


def _remove_sync(image_bytes: bytes) -> bytes:
    from rembg import remove

    session = _get_session()
    result: bytes = remove(image_bytes, session=session)
    return result


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/remove")
async def remove_bg(request: Request) -> Response:
    image_bytes = await request.body()
    logger.info("remove request: %d bytes", len(image_bytes))
    async with _inference_semaphore:
        result = await asyncio.to_thread(_remove_sync, image_bytes)
    logger.info("remove complete: %d bytes", len(result))
    return Response(content=result, media_type="image/png")
