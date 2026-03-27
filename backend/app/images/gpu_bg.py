"""GPU-accelerated background removal using RMBG-2.0 (BiRefNet architecture) via PyTorch + CUDA."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
import torch
from PIL import Image
from torchvision import transforms

logger = structlog.get_logger()

_model: Any = None
_device: torch.device | None = None
_transform: transforms.Compose | None = None
_load_lock = threading.Lock()

# Serialize GPU inference — one call saturates the GPU; concurrent calls risk OOM.
_inference_semaphore: asyncio.Semaphore | None = None


def _load_model() -> tuple[Any, torch.device, transforms.Compose]:
    global _model, _device, _transform
    if _model is not None:
        return _model, _device, _transform  # type: ignore[return-value]

    with _load_lock:
        if _model is not None:
            return _model, _device, _transform  # type: ignore[return-value]

        from transformers import AutoModelForImageSegmentation

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("bg_model_loading", model=settings.bg_removal_model, device=str(_device))

        from app.config import settings

        _model = AutoModelForImageSegmentation.from_pretrained(
            settings.bg_removal_model,
            trust_remote_code=True,
        )
        _model.to(_device).eval()
        if _device.type == "cuda":
            _model.half()

        _transform = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        logger.info(
            "bg_model_loaded",
            model=settings.bg_removal_model,
            device=str(_device),
            dtype="float16" if _device.type == "cuda" else "float32",
        )
        return _model, _device, _transform


def _remove_bg_sync(image_bytes: bytes) -> bytes:
    """Run BiRefNet inference synchronously. Call from a thread."""
    model, device, transform = _load_model()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_size = img.size

    input_tensor = transform(img).unsqueeze(0).to(device)  # type: ignore[union-attr]
    if device.type == "cuda":  # type: ignore[union-attr]
        input_tensor = input_tensor.half()

    with torch.no_grad():
        preds = model(input_tensor)[-1].sigmoid().cpu()

    mask = transforms.ToPILImage()(preds[0].squeeze())
    mask = mask.resize(orig_size, Image.Resampling.LANCZOS)

    result = img.convert("RGBA")
    result.putalpha(mask)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def make_gpu_remover() -> Callable[[bytes], Awaitable[bytes]]:
    """Return an async callable that removes backgrounds via BiRefNet on GPU."""
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
