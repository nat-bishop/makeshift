"""Background removal via BiRefNet-lite (in-process, native CUDA)."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np
import structlog
import torch
from PIL import Image

logger = structlog.get_logger()

_model: Any = None
_transform: Any = None
_device: str = "cpu"
_load_lock = threading.Lock()


def _get_model() -> tuple[Any, Any, str]:
    """Lazy-load BiRefNet-lite with thread-safe singleton."""
    global _model, _transform, _device
    if _model is not None:
        return _model, _transform, _device

    with _load_lock:
        if _model is not None:
            return _model, _transform, _device

        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("birefnet_loading", device=_device)

        _model = AutoModelForImageSegmentation.from_pretrained(
            "ZhengPeng7/BiRefNet_lite",
            trust_remote_code=True,
            dtype=torch.float32,
        )
        _model.to(_device)
        _model.eval()

        _transform = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        logger.info("birefnet_loaded", device=_device)
        return _model, _transform, _device


@torch.no_grad()
def _remove_sync(image_bytes: bytes) -> bytes:
    model, transform, device = _get_model()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_size = img.size

    input_tensor = transform(img).unsqueeze(0).to(device)
    preds = model(input_tensor)[-1].sigmoid().cpu()
    mask = preds[0].squeeze()

    mask_pil = Image.fromarray((mask.numpy() * 255).astype(np.uint8), mode="L")
    mask_pil = mask_pil.resize(orig_size, Image.Resampling.LANCZOS)

    result = img.convert("RGBA")
    result.putalpha(mask_pil)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def make_birefnet_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via in-process BiRefNet-lite."""

    async def remove_bg(image_bytes: bytes) -> bytes:
        logger.debug("birefnet_bg_removal_start", input_size=len(image_bytes))
        result = await asyncio.to_thread(_remove_sync, image_bytes)
        logger.debug("birefnet_bg_removal_complete", output_size=len(result))
        return result

    return remove_bg
