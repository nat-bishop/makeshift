"""Tests for Gemini image generation client."""

from __future__ import annotations

import io
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

import app.images.gemini_client as gemini_client
from app.images.gemini_client import _ensure_png, generate_image


def _make_png_bytes() -> bytes:
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (4, 4), (0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_client() -> Iterator[None]:
    gemini_client._client = None
    yield
    gemini_client._client = None


# --- _ensure_png tests (pure function, no mocking) ---


def test_ensure_png_passthrough_for_png() -> None:
    """PNG input is returned as-is (same bytes object)."""
    png = _make_png_bytes()
    result = _ensure_png(png)
    assert result is png


def test_ensure_png_converts_jpeg_to_png() -> None:
    """JPEG input is converted to PNG format."""
    jpeg = _make_jpeg_bytes()
    result = _ensure_png(jpeg)
    assert result[:4] == b"\x89PNG"
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"


# --- generate_image tests (all mock _get_client) ---


async def test_generate_image_success() -> None:
    """Successful generation returns PNG bytes."""
    png = _make_png_bytes()

    mock_part = MagicMock()
    mock_part.inline_data.data = png

    mock_response = MagicMock()
    mock_response.parts = [mock_part]

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(gemini_client, "_get_client", return_value=mock_client):
        result = await generate_image("a red sword")

    assert result[:4] == b"\x89PNG"
    assert result == png
    mock_client.aio.models.generate_content.assert_awaited_once()


async def test_generate_image_blocked_response() -> None:
    """Response with parts=None raises ValueError mentioning 'blocked'."""
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "SAFETY"

    mock_response = MagicMock()
    mock_response.parts = None
    mock_response.candidates = [mock_candidate]

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(gemini_client, "_get_client", return_value=mock_client):
        with pytest.raises(ValueError, match="blocked.*SAFETY"):
            await generate_image("something blocked")


async def test_generate_image_no_image_data() -> None:
    """Response with parts but no inline_data raises ValueError."""
    mock_part = MagicMock()
    mock_part.inline_data = None

    mock_response = MagicMock()
    mock_response.parts = [mock_part]

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(gemini_client, "_get_client", return_value=mock_client):
        with pytest.raises(ValueError, match="No image data"):
            await generate_image("test prompt")


async def test_generate_image_api_error() -> None:
    """Gemini APIError is re-raised as RuntimeError."""
    from google.genai import errors as genai_errors

    api_error = genai_errors.APIError(
        code=429,
        response_json={"message": "rate limited", "status": "RESOURCE_EXHAUSTED"},
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=api_error)

    with patch.object(gemini_client, "_get_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="Gemini API 429"):
            await generate_image("test prompt")
