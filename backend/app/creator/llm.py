"""Thin LLM call wrappers for V3. All LLM calls go through here.

Uses PydanticAI agents with typed output:
  - int/float/bool: NativeOutput (response_format json_schema, no tool calls)
  - str: plain text mode (model responds directly, no tool call)
Each ask_* function handles clamping and error fallback.
"""

from __future__ import annotations

import structlog
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings as _settings

logger = structlog.get_logger()

# One agent per output type — int/float use NativeOutput (json_schema constrained),
# str uses plain text. Lazy singletons, cleared via reset_agents().
_int_agent: Agent[None, int] | None = None
_float_agent: Agent[None, float] | None = None
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


def _base_model_settings() -> dict:
    """Build model settings from config profile + thinking control."""
    s = _settings
    settings: dict = {
        "temperature": s.llm_temperature,
        "top_p": s.llm_top_p,
        "presence_penalty": s.llm_presence_penalty,
    }
    if s.local_llm_url:
        settings["extra_body"] = {
            "top_k": s.llm_top_k,
            "min_p": s.llm_min_p,
            "repetition_penalty": s.llm_repetition_penalty,
            "chat_template_kwargs": {
                "enable_thinking": not s.local_llm_thinking_disabled,
            },
        }
    return settings


# Max tokens for structured output — caps xgrammar generation to prevent
# infinite whitespace loops (known SGLang/xgrammar bug). JSON like
# {"response": 50000} needs ~15 tokens; 30 gives comfortable headroom.
_STRUCTURED_MAX_TOKENS = 30


def _get_int_agent() -> Agent[None, int]:
    global _int_agent
    if _int_agent is None:
        settings = _base_model_settings()
        settings["max_tokens"] = _STRUCTURED_MAX_TOKENS
        _int_agent = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(int),
            retries=2,
            model_settings=settings,
        )
    return _int_agent


def _get_float_agent() -> Agent[None, float]:
    global _float_agent
    if _float_agent is None:
        settings = _base_model_settings()
        settings["max_tokens"] = _STRUCTURED_MAX_TOKENS
        _float_agent = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(float),
            retries=2,
            model_settings=settings,
        )
    return _float_agent


def _get_str_agent() -> Agent[None, str]:
    global _str_agent
    if _str_agent is None:
        _str_agent = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=str,
            retries=2,
            model_settings=_base_model_settings(),
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
        logger.warning("ask_bool_failed", prompt=prompt[:80], default=default)
        return default


async def ask_text(prompt: str, max_tokens: int = 40, default: str = "") -> str:
    """Ask a freeform text question. Plain text mode (no tool call)."""
    try:
        settings = _base_model_settings()
        settings["temperature"] = 0.7
        settings["max_tokens"] = max_tokens
        result = await _get_str_agent().run(prompt, model_settings=settings)  # type: ignore[call-overload]
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
