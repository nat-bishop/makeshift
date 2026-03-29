"""Tests for image backend modules: local FLUX, fal.ai helpers, fal image gen, cloud BG removal."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.images.fal_helpers as fal_helpers
import app.images.local_image as local_image
from app.images.cloud_bg import make_cloud_remover


@pytest.fixture(autouse=True)
def _reset_singletons():
    local_image._http_client = None
    fal_helpers._http_client = None
    yield
    local_image._http_client = None
    fal_helpers._http_client = None


def _make_fal_mocks(
    fal_result: dict, download_content: bytes
) -> tuple[AsyncMock, MagicMock]:
    """Build a mock fal handler and a mock HTTP client for submit_and_download tests."""
    mock_handler = AsyncMock()
    mock_handler.get.return_value = fal_result

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = download_content

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_handler, mock_client


# ---------------------------------------------------------------------------
# TestLocalImage
# ---------------------------------------------------------------------------


class TestLocalImage:
    async def test_generate_image_success(self) -> None:
        fake_b64 = base64.b64encode(b"fake_image").decode()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"b64_json": fake_b64}]}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(local_image, "_get_http_client", return_value=mock_client):
            result = await local_image.generate_image("a red sword")

        assert result == b"fake_image"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/v1/images/generations"
        payload = call_args[1]["json"]
        assert payload["prompt"] == "a red sword"
        assert payload["response_format"] == "b64_json"

    async def test_close_http_client_idempotent(self) -> None:
        assert local_image._http_client is None
        await local_image.close_http_client()
        assert local_image._http_client is None

    async def test_close_http_client_closes_existing(self) -> None:
        mock_client = AsyncMock()
        local_image._http_client = mock_client
        await local_image.close_http_client()
        mock_client.aclose.assert_awaited_once()
        assert local_image._http_client is None


# ---------------------------------------------------------------------------
# TestFalHelpers
# ---------------------------------------------------------------------------


class TestFalHelpers:
    async def test_submit_and_download_images_key(self) -> None:
        mock_handler, mock_client = _make_fal_mocks(
            {"images": [{"url": "https://example.com/img.png"}]}, b"image_bytes"
        )

        with (
            patch("app.images.fal_helpers.fal_client.submit_async", new_callable=AsyncMock)
            as mock_submit,
            patch.object(fal_helpers, "_get_http_client", return_value=mock_client),
        ):
            mock_submit.return_value = mock_handler
            result = await fal_helpers.submit_and_download(
                "fal-ai/flux-pro/v1.1",
                arguments={"prompt": "test"},
                result_key="images",
            )

        assert result == b"image_bytes"
        mock_submit.assert_awaited_once_with(
            "fal-ai/flux-pro/v1.1", arguments={"prompt": "test"}
        )
        mock_client.get.assert_awaited_once_with("https://example.com/img.png")

    async def test_submit_and_download_image_key(self) -> None:
        mock_handler, mock_client = _make_fal_mocks(
            {"image": {"url": "https://example.com/single.png"}}, b"single_image"
        )

        with (
            patch("app.images.fal_helpers.fal_client.submit_async", new_callable=AsyncMock)
            as mock_submit,
            patch.object(fal_helpers, "_get_http_client", return_value=mock_client),
        ):
            mock_submit.return_value = mock_handler
            result = await fal_helpers.submit_and_download(
                "fal-ai/birefnet",
                arguments={"image_url": "data:image/png;base64,abc"},
                result_key="image",
            )

        assert result == b"single_image"
        mock_client.get.assert_awaited_once_with("https://example.com/single.png")

    async def test_submit_and_download_empty_images(self) -> None:
        mock_handler = AsyncMock()
        mock_handler.get.return_value = {"images": []}

        with patch(
            "app.images.fal_helpers.fal_client.submit_async", new_callable=AsyncMock
        ) as mock_submit:
            mock_submit.return_value = mock_handler
            with pytest.raises(ValueError, match="No 'images' in fal.ai response"):
                await fal_helpers.submit_and_download(
                    "fal-ai/flux-pro/v1.1",
                    arguments={"prompt": "test"},
                    result_key="images",
                )

    async def test_submit_and_download_empty_image(self) -> None:
        mock_handler = AsyncMock()
        mock_handler.get.return_value = {"image": None}

        with patch(
            "app.images.fal_helpers.fal_client.submit_async", new_callable=AsyncMock
        ) as mock_submit:
            mock_submit.return_value = mock_handler
            with pytest.raises(ValueError, match="No 'image' in fal.ai response"):
                await fal_helpers.submit_and_download(
                    "fal-ai/birefnet",
                    arguments={"image_url": "data:image/png;base64,abc"},
                    result_key="image",
                )

    async def test_close_http_client_idempotent(self) -> None:
        assert fal_helpers._http_client is None
        await fal_helpers.close_http_client()
        assert fal_helpers._http_client is None

    async def test_close_http_client_closes_existing(self) -> None:
        mock_client = AsyncMock()
        fal_helpers._http_client = mock_client
        await fal_helpers.close_http_client()
        mock_client.aclose.assert_awaited_once()
        assert fal_helpers._http_client is None


# ---------------------------------------------------------------------------
# TestCloudBg
# ---------------------------------------------------------------------------


class TestCloudBg:
    def test_make_cloud_remover_returns_callable(self) -> None:
        remover = make_cloud_remover()
        assert callable(remover)

    async def test_cloud_remover_calls_submit_and_download(self) -> None:
        with patch(
            "app.images.cloud_bg.submit_and_download", new_callable=AsyncMock
        ) as mock_submit:
            mock_submit.return_value = b"result"
            remover = make_cloud_remover()
            result = await remover(b"input_image")

        assert result == b"result"
        mock_submit.assert_awaited_once()
        call_kwargs = mock_submit.call_args
        assert call_kwargs[0][0] == "fal-ai/birefnet"
        assert call_kwargs[1]["result_key"] == "image"
        arguments = call_kwargs[1]["arguments"]
        assert arguments["image_url"].startswith("data:image/png;base64,")
        assert arguments["model"] == "General Use (Light)"
        assert arguments["operating_resolution"] == "1024x1024"
        expected_b64 = base64.b64encode(b"input_image").decode()
        assert expected_b64 in arguments["image_url"]
