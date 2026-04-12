"""Tests for the local FLUX image backend (generation + img2img edits)."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import app.images.local_image as local_image
import pytest


@pytest.fixture(autouse=True)
def _reset_http_client():
    local_image._http_client = None
    yield
    local_image._http_client = None


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
        assert payload["size"] == "512x512"

    async def test_generate_image_edit_two_refs(self) -> None:
        fake_b64 = base64.b64encode(b"edited_image").decode()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"b64_json": fake_b64}]}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        images = [("char.png", b"char_bytes"), ("obj.png", b"obj_bytes")]
        with patch.object(local_image, "_get_http_client", return_value=mock_client):
            result = await local_image.generate_image_edit("character carrying object", images)

        assert result == b"edited_image"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/v1/images/edits"
        # Verify multipart form data -- both images sent as separate file parts
        files = call_args[1]["files"]
        assert len(files) == 2
        assert files[0][0] == "image"
        assert files[0][1] == ("char.png", b"char_bytes", "image/png")
        assert files[1][1] == ("obj.png", b"obj_bytes", "image/png")
        # Verify form data payload (not JSON -- all string values)
        data = call_args[1]["data"]
        assert data["prompt"] == "character carrying object"
        assert data["n"] == "1"
        assert data["size"] == "512x512"
        assert data["response_format"] == "b64_json"

    async def test_generate_image_edit_single_ref(self) -> None:
        """Destruction use case: only one reference image."""
        fake_b64 = base64.b64encode(b"destruction").decode()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"b64_json": fake_b64}]}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(local_image, "_get_http_client", return_value=mock_client):
            result = await local_image.generate_image_edit(
                "pile of debris", [("object.png", b"object_bytes")]
            )

        assert result == b"destruction"
        files = mock_client.post.call_args[1]["files"]
        assert len(files) == 1
        assert files[0][1] == ("object.png", b"object_bytes", "image/png")

    async def test_close_http_client_idempotent(self) -> None:
        local_image._http_client = None
        await local_image.close_http_client()
        assert local_image._http_client is None

    async def test_close_http_client_closes_existing(self) -> None:
        mock_client = AsyncMock()
        local_image._http_client = mock_client
        await local_image.close_http_client()
        mock_client.aclose.assert_awaited_once()
        assert local_image._http_client is None
