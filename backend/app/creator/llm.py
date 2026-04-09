"""Thin LLM call wrappers for V3. All LLM calls go through here.

Uses PydanticAI agents with typed output:
  - int/float: NativeOutput with bounded types (json_schema with min/max,
    prevents xgrammar from generating unbounded digit sequences)
  - str: plain text mode (model responds directly, no tool call)
Each ask_* function handles clamping and error fallback.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from annotated_types import Ge, Le
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings as _settings

logger = structlog.get_logger()

# Bounded types — xgrammar uses schema min/max to limit digit generation.
# Without bounds, the model can generate numbers with thousands of digits
# (each digit = one forward pass), causing apparent hangs.
BoundedInt = Annotated[int, Ge(-1_000_000), Le(1_000_000)]
BoundedFloat = Annotated[float, Ge(-1_000_000), Le(1_000_000)]

# One agent per output type. Lazy singletons, cleared via reset_agents().
_int_agent: Agent[None, BoundedInt] | None = None
_float_agent: Agent[None, BoundedFloat] | None = None
_str_agent: Agent[None, str] | None = None


def _build_model():
    """Route to local SGLang (OpenAI-compatible) or cloud API."""
    s = _settings
    if s.local_llm_url:
        return OpenAIChatModel(
            s.llm_model,
            provider=OpenAIProvider(base_url=s.local_llm_url, api_key="unused"),
            profile=OpenAIModelProfile(supports_json_schema_output=True),
        )
    return s.llm_model


def _get_int_agent() -> Agent[None, BoundedInt]:
    global _int_agent
    if _int_agent is None:
        _int_agent = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(BoundedInt),
            retries=2,
            model_settings={"temperature": 0.0},
        )
    return _int_agent


def _get_float_agent() -> Agent[None, BoundedFloat]:
    global _float_agent
    if _float_agent is None:
        _float_agent = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(BoundedFloat),
            retries=2,
            model_settings={"temperature": 0.0},
        )
    return _float_agent


def _get_str_agent() -> Agent[None, str]:
    global _str_agent
    if _str_agent is None:
        _str_agent = Agent(  # type: ignore[call-overload]
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
    """Ask a numeric question (e.g. mass in kg). Returns clamped value or default."""
    try:
        result = await _get_float_agent().run(prompt)
        return max(lo, min(hi, result.output))
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


async def ask_text(prompt: str, max_tokens: int = 40, default: str = "") -> str:
    """Ask a freeform text question. Plain text mode (no tool call)."""
    try:
        result = await _get_str_agent().run(
            prompt, model_settings={"temperature": 0.0, "max_tokens": max_tokens}
        )  # type: ignore[call-overload]
        return result.output.strip() or default
    except Exception:
        logger.warning("ask_text_failed", prompt=prompt[:80])
        return default


def reset_agents() -> None:
    """Clear cached agents (for testing or model swap)."""
    global _int_agent, _float_agent, _str_agent
    _int_agent = None
    _float_agent = None
    _str_agent = None
