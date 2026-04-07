from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = structlog.get_logger()


def build_model() -> Model | str:
    """Build PydanticAI model from config. Used by both old agent and new pipeline."""
    if settings.local_llm_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model = OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
        )
        logger.info("llm_model_built", model=settings.llm_model, base_url=settings.local_llm_url)
        return model

    logger.info("llm_model_built", model=settings.llm_model)
    return settings.llm_model
