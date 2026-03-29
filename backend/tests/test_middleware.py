"""Tests for session context middleware: session ID extraction, contextvars, slow-request logging."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.middleware import session_context_middleware


def _make_request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    request.method = "GET"
    return request


def _make_response(status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    return response


@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
async def test_session_id_extracted_from_api_sessions_path(
    mock_bind: MagicMock,
    mock_clear: MagicMock,
) -> None:
    request = _make_request("/api/sessions/abc-123/objects")
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_bind.assert_called_once_with(session_id="abc-123")


@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
async def test_session_id_extracted_from_ws_path(
    mock_bind: MagicMock,
    mock_clear: MagicMock,
) -> None:
    request = _make_request("/ws/abc-123")
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_bind.assert_called_once_with(session_id="abc-123")


@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
@pytest.mark.parametrize("path", ["/api/rules", "/health"])
async def test_no_bind_for_non_session_paths(
    mock_bind: MagicMock,
    mock_clear: MagicMock,
    path: str,
) -> None:
    request = _make_request(path)
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_bind.assert_not_called()


@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
async def test_clear_contextvars_called_on_success(
    mock_bind: MagicMock,
    mock_clear: MagicMock,
) -> None:
    request = _make_request("/api/sessions/s1/objects")
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_clear.assert_called_once()


@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
async def test_clear_contextvars_called_when_call_next_raises(
    mock_bind: MagicMock,
    mock_clear: MagicMock,
) -> None:
    request = _make_request("/api/sessions/s1/objects")
    call_next = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await session_context_middleware(request, call_next)

    mock_clear.assert_called_once()


@patch("app.middleware.logger")
@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
@patch("app.middleware.time.monotonic")
async def test_slow_request_logs_warning(
    mock_monotonic: MagicMock,
    mock_bind: MagicMock,
    mock_clear: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_monotonic.side_effect = [0.0, 1.5]
    request = _make_request("/api/sessions/s1/objects")
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_logger.warning.assert_called_once()
    args, kwargs = mock_logger.warning.call_args
    assert args[0] == "slow_request"
    assert kwargs["elapsed"] == 1.5


@patch("app.middleware.logger")
@patch("app.middleware.structlog.contextvars.clear_contextvars")
@patch("app.middleware.structlog.contextvars.bind_contextvars")
@patch("app.middleware.time.monotonic")
async def test_normal_request_no_warning(
    mock_monotonic: MagicMock,
    mock_bind: MagicMock,
    mock_clear: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_monotonic.side_effect = [0.0, 0.1]
    request = _make_request("/health")
    call_next = AsyncMock(return_value=_make_response())

    await session_context_middleware(request, call_next)

    mock_logger.warning.assert_not_called()
