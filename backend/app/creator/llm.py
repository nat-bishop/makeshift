"""Thin LLM call wrappers for V3. All LLM calls go through here.

Uses PydanticAI agents with typed output:
  - int/float/bool: NativeOutput (response_format json_schema, no tool calls)
  - choice: constrained decoding via Literal output type
  - str: plain text mode (model responds directly, no tool call)
Each ask_* function handles clamping and error fallback.

One singleton Agent per output type. Per-call system prompts are passed via
the ``instructions`` parameter on ``agent.run()``, not by constructing
throwaway agents.
"""

from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings as _settings

logger = structlog.get_logger()

# Agent caches — keyed by output schema. Cleared via reset_agents().
_numeric_agents: dict[type[BaseModel], Agent] = {}
_str_agent: Agent[None, str] | None = None
_choice_agents: dict[tuple[str, ...], Agent] = {}


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
# With bounded schemas (Field ge/le), xgrammar enforces min/max at the
# grammar level so outputs stay within range and within token budget.
_STRUCTURED_MAX_TOKENS = 30


# Bounded output model factories — Field(ge, le) emits minimum/maximum
# in JSON schema, which xgrammar enforces at the grammar level.
_bounded_int_models: dict[tuple[int, int], type[BaseModel]] = {}
_bounded_float_models: dict[tuple[float, float], type[BaseModel]] = {}


def _bounded_int_model(lo: int, hi: int) -> type[BaseModel]:
    key = (lo, hi)
    if key not in _bounded_int_models:

        class BoundedInt(BaseModel):
            response: int = Field(ge=lo, le=hi)

        _bounded_int_models[key] = BoundedInt
    return _bounded_int_models[key]


def _bounded_float_model(lo: float, hi: float) -> type[BaseModel]:
    key = (lo, hi)
    if key not in _bounded_float_models:

        class BoundedFloat(BaseModel):
            response: float = Field(ge=lo, le=hi)

        _bounded_float_models[key] = BoundedFloat
    return _bounded_float_models[key]


def _get_numeric_agent(model_cls: type[BaseModel]) -> Agent:
    if model_cls not in _numeric_agents:
        settings = _base_model_settings()
        settings["max_tokens"] = _STRUCTURED_MAX_TOKENS
        _numeric_agents[model_cls] = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(model_cls),
            retries=2,
            model_settings=settings,
        )
    return _numeric_agents[model_cls]


def _get_choice_agent(choices: tuple[str, ...]) -> Agent:
    """Get or create a constrained-choice agent for the given vocabulary."""
    if choices not in _choice_agents:
        literal_type = Literal[choices]  # type: ignore[valid-type]
        settings = _base_model_settings()
        settings["max_tokens"] = _STRUCTURED_MAX_TOKENS
        _choice_agents[choices] = Agent(  # type: ignore[call-overload]
            _build_model(),
            output_type=NativeOutput(literal_type),
            retries=2,
            model_settings=settings,
        )
    return _choice_agents[choices]


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


async def ask_int(
    prompt: str,
    lo: int = 0,
    hi: int = 100,
    default: int = 50,
    *,
    instructions: str = "",
) -> int:
    """Ask a bounded integer question. Schema enforces [lo, hi] via xgrammar."""
    try:
        agent = _get_numeric_agent(_bounded_int_model(lo, hi))
        result = await agent.run(prompt, instructions=instructions or None)
        return result.output.response  # type: ignore[attr-defined,no-any-return]
    except Exception as e:
        logger.warning("ask_int_failed", prompt=prompt[:60], default=default, error=str(e)[:200])
        return default


async def ask_float(
    prompt: str,
    lo: float = 0.001,
    hi: float = 100000.0,
    default: float = 1.0,
    *,
    instructions: str = "",
) -> float:
    """Ask a bounded float question. Schema enforces [lo, hi] via xgrammar."""
    try:
        agent = _get_numeric_agent(_bounded_float_model(lo, hi))
        result = await agent.run(prompt, instructions=instructions or None)
        return result.output.response  # type: ignore[attr-defined,no-any-return]
    except Exception as e:
        logger.warning("ask_float_failed", prompt=prompt[:60], default=default, error=str(e)[:200])
        return default


async def ask_bool(prompt: str, default: bool = False) -> bool:
    """Ask a 0/1 question. Returns True if output is 1."""
    try:
        agent = _get_numeric_agent(_bounded_int_model(0, 1))
        result = await agent.run(prompt)
        return result.output.response == 1  # type: ignore[attr-defined,no-any-return]
    except Exception:
        logger.warning("ask_bool_failed", prompt=prompt[:80], default=default)
        return default


async def ask_choice(
    prompt: str,
    choices: tuple[str, ...],
    default: str = "",
    *,
    instructions: str = "",
) -> str:
    """Constrained output from a fixed vocabulary. Returns the chosen word."""
    try:
        result = await _get_choice_agent(choices).run(prompt, instructions=instructions or None)
        return result.output
    except Exception as e:
        logger.warning(
            "ask_choice_failed",
            prompt=prompt[:60],
            choices=choices,
            default=default,
            error=str(e)[:200],
        )
        return default


async def ask_text(
    prompt: str, max_tokens: int = 40, default: str = "", *, instructions: str = ""
) -> str:
    """Ask a freeform text question. Plain text mode (no structured output)."""
    try:
        settings = _base_model_settings()
        settings["temperature"] = 0.7
        settings["max_tokens"] = max_tokens
        result = await _get_str_agent().run(
            prompt,
            instructions=instructions or None,
            model_settings=settings,
        )  # type: ignore[call-overload]
        return result.output.strip() or default
    except Exception:
        logger.warning("ask_text_failed", prompt=prompt[:80])
        return default


def reset_agents() -> None:
    """Clear cached agents (for testing or model swap)."""
    global _str_agent
    _numeric_agents.clear()
    _str_agent = None
    _choice_agents.clear()
