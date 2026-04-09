"""Tests for LLM wrapper functions (creator/llm.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import app.creator.llm as llm_module
import pytest
from app.creator.llm import (
    ask_bool,
    ask_float,
    ask_int,
    ask_text,
    reset_agents,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_agents() -> Iterator[None]:
    reset_agents()
    yield
    reset_agents()


def _fake_agent(output: object) -> MagicMock:
    """Return a mock agent whose .run() resolves to a result with .output set."""
    result = MagicMock()
    result.output = output
    agent = MagicMock()
    agent.run = AsyncMock(return_value=result)
    return agent


def _failing_agent() -> MagicMock:
    """Return a mock agent whose .run() raises RuntimeError."""
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))
    return agent


# --- ask_int ---


async def test_ask_int_clamps_above_hi() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(200)):
        assert await ask_int("how heavy?", lo=0, hi=100) == 100


async def test_ask_int_clamps_below_lo() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(-5)):
        assert await ask_int("how heavy?", lo=0, hi=100) == 0


async def test_ask_int_returns_value_in_range() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(42)):
        assert await ask_int("how heavy?", lo=0, hi=100) == 42


async def test_ask_int_failure_returns_default() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_failing_agent()):
        assert await ask_int("how heavy?", default=50) == 50


# --- ask_float ---


async def test_ask_float_clamps_above_hi() -> None:
    with patch.object(llm_module, "_get_float_agent", return_value=_fake_agent(999999.0)):
        assert await ask_float("mass in kg?", lo=0.001, hi=100.0) == 100.0


async def test_ask_float_clamps_below_lo() -> None:
    with patch.object(llm_module, "_get_float_agent", return_value=_fake_agent(-0.5)):
        assert await ask_float("mass in kg?", lo=0.001, hi=100.0) == 0.001


async def test_ask_float_returns_value_in_range() -> None:
    with patch.object(llm_module, "_get_float_agent", return_value=_fake_agent(3.14)):
        assert await ask_float("mass in kg?", lo=0.001, hi=100.0) == pytest.approx(3.14)


async def test_ask_float_failure_returns_default() -> None:
    with patch.object(llm_module, "_get_float_agent", return_value=_failing_agent()):
        assert await ask_float("mass in kg?", default=1.0) == 1.0


# --- ask_bool ---


async def test_ask_bool_returns_true_when_output_is_1() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(1)):
        assert await ask_bool("is it alive?") is True


async def test_ask_bool_returns_false_when_output_is_0() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(0)):
        assert await ask_bool("is it alive?") is False


async def test_ask_bool_returns_false_for_other_values() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_fake_agent(42)):
        assert await ask_bool("is it alive?") is False


async def test_ask_bool_failure_returns_default_false() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_failing_agent()):
        assert await ask_bool("is it alive?") is False


async def test_ask_bool_failure_returns_default_true() -> None:
    with patch.object(llm_module, "_get_int_agent", return_value=_failing_agent()):
        assert await ask_bool("is it alive?", default=True) is True


# --- ask_text ---


async def test_ask_text_success_strips_whitespace() -> None:
    with patch.object(llm_module, "_get_str_agent", return_value=_fake_agent("  hello world  ")):
        assert await ask_text("describe it") == "hello world"


async def test_ask_text_empty_returns_default() -> None:
    with patch.object(llm_module, "_get_str_agent", return_value=_fake_agent("   ")):
        assert await ask_text("describe it", default="unknown") == "unknown"


async def test_ask_text_failure_returns_default() -> None:
    with patch.object(llm_module, "_get_str_agent", return_value=_failing_agent()):
        assert await ask_text("describe it", default="fallback") == "fallback"


# --- reset_agents ---


def test_reset_agents_clears_singletons() -> None:
    llm_module._int_agent = MagicMock()  # type: ignore[assignment]
    llm_module._float_agent = MagicMock()  # type: ignore[assignment]
    llm_module._str_agent = MagicMock()  # type: ignore[assignment]

    reset_agents()

    assert llm_module._int_agent is None
    assert llm_module._float_agent is None
    assert llm_module._str_agent is None
