"""Shared fixtures and judge model for creator agent evals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.models.blueprint import CreatorOutputSpec
    from pydantic_ai import Agent

JUDGE_MODEL = "google-gla:gemini-3-flash-preview"

set_default_judge_model(JUDGE_MODEL)


def make_agent(system_prompt: str) -> Agent[None, CreatorOutputSpec]:
    """Build a fresh PydanticAI agent with the given system prompt.

    Uses the same model and settings as production (from .env),
    but with a custom system prompt for evaluation.
    """
    from app.creator.agent import _build_model
    from app.models.blueprint import CreatorOutputSpec
    from pydantic_ai import Agent

    model_settings: dict = {
        "timeout": settings.llm_timeout_seconds,
        "temperature": settings.llm_temperature,
        "top_p": settings.llm_top_p,
        "presence_penalty": settings.llm_presence_penalty,
    }
    if settings.local_llm_url:
        model_settings["extra_body"] = {
            "top_k": settings.llm_top_k,
            "min_p": settings.llm_min_p,
            "repetition_penalty": settings.llm_repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": not settings.local_llm_thinking_disabled},
        }

    return Agent(
        _build_model(),
        output_type=CreatorOutputSpec,
        retries=3,
        system_prompt=system_prompt,
        model_settings=model_settings,
    )


def make_task(agent: Agent[None, CreatorOutputSpec]) -> Callable[[str], Awaitable[str]]:
    """Wrap a PydanticAI agent as a pydantic-evals task function."""

    async def task(description: str) -> str:
        result = await agent.run(f"Create a game object for: {description}")
        return result.output.model_dump_json(indent=2)

    return task
