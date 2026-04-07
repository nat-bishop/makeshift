"""Shared fixtures and judge model for creator agent evals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import settings
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import BaseModel
    from pydantic_ai import Agent

JUDGE_MODEL = "google-gla:gemini-3-flash-preview"

set_default_judge_model(JUDGE_MODEL)


def make_agent(
    system_prompt: str,
    output_type: type[BaseModel] | None = None,
) -> Agent[None, Any]:
    """Build a fresh PydanticAI agent with the given system prompt.

    Uses the same model and settings as production (from .env),
    but with a custom system prompt for evaluation.
    """
    from app.creator.agent import _build_model
    from app.models.blueprint import CreatorOutput
    from pydantic_ai import Agent

    result_type = output_type or CreatorOutput

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
        output_type=result_type,
        retries=3,
        system_prompt=system_prompt,
        model_settings=model_settings,
    )


def make_task(agent: Agent[None, Any]) -> Callable[[str], Awaitable[str]]:
    """Wrap a PydanticAI agent as a pydantic-evals task function.

    Records retry count via set_eval_attribute so it appears in
    ReportCase.attributes["retries"] — works without logfire.
    """
    from pydantic_ai.messages import ModelRequest, RetryPromptPart
    from pydantic_evals import set_eval_attribute

    async def task(description: str) -> str:
        result = await agent.run(f"Create a game object for: {description}")
        set_eval_attribute("retries", result.usage().requests - 1)

        retry_errors = []
        for msg in result.all_messages():
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, RetryPromptPart):
                        retry_errors.append(str(part.content))
        set_eval_attribute("retry_errors", retry_errors)

        return result.output.model_dump_json(indent=2)

    return task


def make_split_task(
    classify_agent: Agent[None, Any],
    creative_agent: Agent[None, Any],
) -> Callable[[str], Awaitable[str]]:
    """Wrap a two-agent split pipeline as a pydantic-evals task.

    Call 1: classify (name, substance, element, tags)
    Call 2: creative (behaviors, visual) given Call 1 output
    Merges into a single CreatorOutput JSON string.
    """
    from pydantic_ai.messages import ModelRequest, RetryPromptPart
    from pydantic_evals import set_eval_attribute

    async def task(description: str) -> str:
        # Call 1: classify
        classify_result = await classify_agent.run(
            f"Classify this game object: {description}"
        )
        classify_out = classify_result.output

        # Build context for Call 2
        tags_str = ", ".join(t.value for t in classify_out.tags) if classify_out.tags else "none"
        element_str = classify_out.element.value if classify_out.element else "none"
        creative_prompt = (
            f"Object: {classify_out.name}\n"
            f"Substance: {classify_out.substance.value}\n"
            f"Element: {element_str}\n"
            f"Tags: [{tags_str}]\n\n"
            f"Player description: {description}\n\n"
            f"Design behaviors and visual for this object."
        )

        # Call 2: creative
        creative_result = await creative_agent.run(creative_prompt)
        creative_out = creative_result.output

        # Track retries from both calls
        total_retries = (
            classify_result.usage().requests - 1
            + creative_result.usage().requests - 1
        )
        set_eval_attribute("retries", total_retries)

        retry_errors = []
        for result in (classify_result, creative_result):
            for msg in result.all_messages():
                if isinstance(msg, ModelRequest):
                    for part in msg.parts:
                        if isinstance(part, RetryPromptPart):
                            retry_errors.append(str(part.content))
        set_eval_attribute("retry_errors", retry_errors)

        # Merge into CreatorOutput-compatible JSON
        merged = {
            "name": classify_out.name,
            "substance": classify_out.substance.value,
            "element": classify_out.element.value if classify_out.element else None,
            "tags": [t.value for t in classify_out.tags],
            "behaviors": [b.model_dump() for b in creative_out.behaviors],
            "visual_descriptor": creative_out.visual_descriptor.model_dump(),
        }
        import json
        return json.dumps(merged, indent=2)

    return task
