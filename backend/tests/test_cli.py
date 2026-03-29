"""Tests for CLI Timer class and _check_health helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.cli import Timer, _check_health


class TestTimer:
    def test_add_accumulates_steps(self) -> None:
        timer = Timer()
        timer.add("step_one", 1.5, "first detail")
        timer.add("step_two", 2.3, "second detail")

        assert len(timer.steps) == 2
        assert timer.steps[0] == ("step_one", 1.5, "first detail")
        assert timer.steps[1] == ("step_two", 2.3, "second detail")

    def test_total_returns_elapsed(self) -> None:
        with patch("app.cli.time.monotonic", side_effect=[100.0, 105.0]):
            timer = Timer()
            assert timer.total == 5.0

    def test_print_summary_outputs_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("app.cli.time.monotonic", side_effect=[100.0, 110.0, 110.0]):
            timer = Timer()
            timer.add("llm", 4.0, "gemini")
            timer.add("image", 6.0)
            timer.print_summary()

        captured = capsys.readouterr()
        stderr = captured.err
        assert "--- timing ---" in stderr
        assert "llm" in stderr
        assert "image" in stderr
        assert "total" in stderr
        assert "gemini" in stderr


class TestCheckHealth:
    async def test_health_ok(self) -> None:
        response = MagicMock(status_code=200)
        client = MagicMock()
        client.get = AsyncMock(return_value=response)

        result = await _check_health(client, "http://example.com/health")
        assert result == "ok"

    async def test_health_error_status(self) -> None:
        response = MagicMock(status_code=500)
        client = MagicMock()
        client.get = AsyncMock(return_value=response)

        result = await _check_health(client, "http://example.com/health")
        assert result == "error (500)"

    async def test_health_unreachable(self) -> None:
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await _check_health(client, "http://example.com/health")
        assert result == "unreachable (ConnectError)"
