from __future__ import annotations

from enum import StrEnum
from typing import Literal

import structlog
from pydantic import BaseModel, Field, field_validator

from app.models.substances import Element, Substance
from app.models.tags import LLM_VISIBLE_TAGS_V2, TAG_DESCRIPTIONS, Tag

logger = structlog.get_logger()

# Pre-computed constants for tag validation
_V2_TAG_VALUES: frozenset[str] = frozenset(t.value for t in LLM_VISIBLE_TAGS_V2)
_V2_TAG_HELP: str = "\n".join(
    f"  {tag.value} — {TAG_DESCRIPTIONS[tag]}"
    for tag in sorted(LLM_VISIBLE_TAGS_V2, key=lambda t: t.value)
)


class BehaviorVerb(StrEnum):
    DESTROY = "destroy"
    EAT = "eat"
    INVESTIGATE = "investigate"
    FOLLOW = "follow"
    PROTECT = "protect"
    FLEE = "flee"


class BehaviorVerbSpec(BaseModel):
    verb: BehaviorVerb
    target: str = Field(min_length=1, max_length=100)


class VisualDescriptor(BaseModel):
    visual_description: str = Field(
        description="1-2 sentences: shape, material, colors, distinctive features"
    )
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = Field(
        description="Scale relative to the player character (small-to-medium sized)"
    )


class CreatorOutput(BaseModel):
    """V2 LLM output: substance + element + tags + behaviors."""

    name: str
    substance: Substance
    element: Element | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=3)
    behaviors: list[BehaviorVerbSpec] = Field(default_factory=list, max_length=4)
    visual_descriptor: VisualDescriptor

    @field_validator("name")
    @classmethod
    def check_name_length(cls, name: str) -> str:
        from pydantic_ai import ModelRetry

        name = name.strip()
        if not name:
            logger.debug("llm_retry_name", reason="empty")
            raise ModelRetry("Name cannot be empty.")
        words = name.split()
        if len(words) > 3:
            logger.debug("llm_retry_name", name=name, word_count=len(words))
            raise ModelRetry(f'Name "{name}" has {len(words)} words. Use 1-3 words maximum.')
        return name

    @field_validator("tags", mode="before")
    @classmethod
    def validate_v2_tags(cls, tags: list) -> list:
        """Only allow V2 LLM-visible tags."""
        from pydantic_ai import ModelRetry

        result = []
        seen: set[str] = set()
        for t in tags:
            val = t.value if isinstance(t, Tag) else str(t).strip().upper()
            if val in seen:
                continue
            seen.add(val)
            if val not in _V2_TAG_VALUES:
                raise ModelRetry(
                    f"Tag '{t}' is not available. V2 tags (pick 0-3):\n{_V2_TAG_HELP}"
                )
            result.append(val)
        return result




class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str
    # V2 fields
    substance: Substance
    element: Element | None = None
    tags: list[Tag]
    behaviors: list[BehaviorVerbSpec] = Field(default_factory=list)
    visual_descriptor: VisualDescriptor
    # Derived data (computed at creation time)
    substance_profile: dict[str, float | str] = Field(default_factory=dict)
    combat_profile: dict[str, float] = Field(default_factory=dict)
    identity_embedding: list[float] = Field(default_factory=list)
    behavior_embeddings: list[list[float]] = Field(default_factory=list)
    starting_durability: int = 150
