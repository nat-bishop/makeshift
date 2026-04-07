"""Thin LLM call wrappers for V3. All LLM calls go through here.

Uses PydanticAI agents with temperature=0 for deterministic 1-token answers.
Each ask_* function handles parsing, clamping, and error fallback.
"""

from __future__ import annotations

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

from app.config import settings as _settings

logger = structlog.get_logger()

_int_agent: Agent[None, int] | None = None
_str_agent: Agent[None, str] | None = None


def _build_model():
    """Route to local SGLang (OpenAI-compatible) or cloud API."""
    s = _settings
    if s.local_llm_url:
        return OpenAIModel(
            model_name=s.llm_model,
            base_url=s.local_llm_url,
        )
    return s.llm_model


def _get_int_agent() -> Agent[None, int]:
    global _int_agent
    if _int_agent is None:
        _int_agent = Agent(
            _build_model(),
            output_type=int,
            retries=2,
            model_settings={"temperature": 0.0},
        )
    return _int_agent


def _get_str_agent() -> Agent[None, str]:
    global _str_agent
    if _str_agent is None:
        _str_agent = Agent(
            _build_model(),
            output_type=str,
            retries=2,
            model_settings={"temperature": 0.0},
        )
    return _str_agent


async def ask_int(prompt: str, lo: int = 0, hi: int = 100, default: int = 50) -> int:
    """Ask a 1-token integer question. Returns clamped value or default on failure."""
    try:
        result = await _get_int_agent().run(prompt)
        return max(lo, min(hi, result.output))
    except Exception:
        logger.warning("ask_int_failed", prompt=prompt[:80], default=default)
        return default


async def ask_float(
    prompt: str, lo: float = 0.001, hi: float = 100000.0, default: float = 1.0
) -> float:
    """Ask a numeric question that may return a decimal (mass in kg). 2-4 tokens."""
    try:
        result = await _get_str_agent().run(prompt)
        cleaned = "".join(c for c in result.output.strip() if c in "0123456789.-")
        val = float(cleaned) if cleaned else default
        return max(lo, min(hi, val))
    except Exception:
        logger.warning("ask_float_failed", prompt=prompt[:80], default=default)
        return default


async def ask_bool(prompt: str, default: bool = False) -> bool:
    """Ask a 0/1 question. Returns True if output is 1."""
    try:
        result = await _get_int_agent().run(prompt)
        return result.output == 1
    except Exception:
        return default


async def ask_text(
    prompt: str, max_tokens: int = 40, default: str = ""
) -> str:
    """Ask a freeform text question. Multi-token output."""
    try:
        result = await _get_str_agent().run(
            prompt, model_settings={"max_tokens": max_tokens}
        )
        return result.output.strip() or default
    except Exception:
        logger.warning("ask_text_failed", prompt=prompt[:80])
        return default


def reset_agents() -> None:
    """Clear cached agents (for testing or model swap)."""
    global _int_agent, _str_agent
    _int_agent = None
    _str_agent = None
