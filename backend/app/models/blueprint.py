from __future__ import annotations

from enum import StrEnum
from typing import Literal

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.substances import Element, Substance
from app.models.tags import BEHAVIOR_TARGETS, LLM_VISIBLE_TAGS, TAG_DESCRIPTIONS, Category, Tag

logger = structlog.get_logger()

# Pre-computed constants for tag validation
_LLM_TAG_VALUES: frozenset[str] = frozenset(t.value for t in LLM_VISIBLE_TAGS)
_LLM_TAG_HELP: str = "\n".join(
    f"  {tag.value} — {TAG_DESCRIPTIONS[tag]}"
    for tag in sorted(LLM_VISIBLE_TAGS, key=lambda t: t.value)
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
    target_description: str = Field(min_length=1, max_length=100)
    target_tag: str = ""

    @field_validator("target_tag", mode="before")
    @classmethod
    def validate_target_tag(cls, val: str) -> str:
        """Validate target_tag against BEHAVIOR_TARGETS (categories + select state tags)."""
        from pydantic_ai import ModelRetry

        if not val:
            return ""
        val = str(val).strip().upper()
        if val not in BEHAVIOR_TARGETS:
            valid = ", ".join(sorted(BEHAVIOR_TARGETS))
            raise ModelRetry(
                f"target_tag '{val}' is not valid. Valid target_tags: {valid}"
            )
        return val

    @model_validator(mode="after")
    def check_aggressive_verbs_have_target(self) -> BehaviorVerbSpec:
        from pydantic_ai import ModelRetry

        aggressive = (BehaviorVerb.DESTROY, BehaviorVerb.EAT, BehaviorVerb.FLEE)
        if self.verb in aggressive and not self.target_tag:
            valid = ", ".join(sorted(BEHAVIOR_TARGETS))
            raise ModelRetry(
                f"'{self.verb.value}' behaviors MUST have a target_tag. "
                f"Valid target_tags: {valid}"
            )
        return self


class VisualDescriptor(BaseModel):
    visual_description: str = Field(
        description="1-2 sentences: shape, material, colors, distinctive features"
    )
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = Field(
        description="Scale relative to the player character (small-to-medium sized)"
    )


class CreatorOutput(BaseModel):
    """LLM output: substance + element + categories + tags + behaviors."""

    name: str
    substance: Substance
    element: Element | None = None
    categories: list[Category] = Field(default_factory=list, max_length=3)
    tags: list[Tag] = Field(default_factory=list, max_length=3)
    behaviors: list[BehaviorVerbSpec] = Field(default_factory=list, max_length=4)
    visual_descriptor: VisualDescriptor

    @field_validator("categories", mode="before")
    @classmethod
    def validate_categories(cls, cats: list) -> list:
        """Validate and deduplicate categories."""
        from pydantic_ai import ModelRetry

        valid = {c.value for c in Category}
        result = []
        seen: set[str] = set()
        for c in cats:
            val = c.value if isinstance(c, Category) else str(c).strip().upper()
            if val in seen:
                continue
            seen.add(val)
            if val not in valid:
                raise ModelRetry(
                    f"Category '{c}' is not valid. Valid categories: {', '.join(sorted(valid))}"
                )
            result.append(val)
        return result

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
    def validate_llm_tags(cls, tags: list) -> list:
        """Only allow LLM-visible tags."""
        from pydantic_ai import ModelRetry

        result = []
        seen: set[str] = set()
        for t in tags:
            val = t.value if isinstance(t, Tag) else str(t).strip().upper()
            if val in seen:
                continue
            seen.add(val)
            if val not in _LLM_TAG_VALUES:
                raise ModelRetry(
                    f"Tag '{t}' is not available. Available tags (pick 0-3):\n{_LLM_TAG_HELP}"
                )
            result.append(val)
        return result




class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str
    # Substance/element fields
    substance: Substance
    element: Element | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[Tag]
    behaviors: list[BehaviorVerbSpec] = Field(default_factory=list)
    visual_descriptor: VisualDescriptor
    # Derived data (computed at creation time)
    substance_profile: dict[str, float | str] = Field(default_factory=dict)
    combat_profile: dict[str, float] = Field(default_factory=dict)
    compiled_behaviors: list[dict] = Field(default_factory=list)
    starting_durability: int = 150
