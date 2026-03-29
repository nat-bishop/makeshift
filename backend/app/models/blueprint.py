from typing import Literal

import structlog
from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.behaviors import (
    BEHAVIOR_BUDGET,
    Behavior,
    BehaviorSpec,
    compute_behavior_cost,
    compute_spec_cost,
)
from app.models.tags import (
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    Tag,
)

DURABILITY_BREAKABLE = 50
DURABILITY_RIGID = 200
DURABILITY_FLEXIBLE = 100
DURABILITY_DEFAULT = 150

logger = structlog.get_logger()


class VisualDescriptor(BaseModel):
    visual_description: str = Field(
        description="1-2 sentences: shape, material, colors, distinctive features"
    )
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = Field(
        description="Scale relative to the player character (small-to-medium sized)"
    )


class CreatorOutput(BaseModel):
    name: str
    tags: list[Tag] = Field(min_length=2, max_length=6)
    behaviors: list[Behavior] = Field(default_factory=list, max_length=3)
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

    @field_validator("tags")
    @classmethod
    def check_contradictions(cls, tags: list[Tag]) -> list[Tag]:
        from pydantic_ai import ModelRetry

        tag_set = set(tags)
        for pair in TAG_CONTRADICTIONS:
            if pair <= tag_set:
                a, b = sorted(pair, key=lambda t: t.value)
                logger.debug("llm_retry_contradiction", tag_a=a.value, tag_b=b.value)
                raise ModelRetry(f"{a.value} and {b.value} cannot coexist. Remove one.")
        return tags

    @field_validator("tags")
    @classmethod
    def check_budget(cls, tags: list[Tag]) -> list[Tag]:
        from pydantic_ai import ModelRetry

        cost = sum(TAG_POWER_COSTS[t] for t in tags)
        if cost > OBJECT_TAG_BUDGET:
            logger.debug("llm_retry_budget", cost=cost, budget=OBJECT_TAG_BUDGET)
            breakdown = ", ".join(f"{t.value}({TAG_POWER_COSTS[t]})" for t in tags)
            raise ModelRetry(
                f"Budget {cost}/{OBJECT_TAG_BUDGET}. Tags: {breakdown}. Remove expensive tags."
            )
        return tags

    @field_validator("behaviors")
    @classmethod
    def check_behavior_budget(cls, behaviors: list[Behavior]) -> list[Behavior]:
        from pydantic_ai import ModelRetry

        if not behaviors:
            return behaviors
        cost = sum(compute_behavior_cost(b) for b in behaviors)
        if cost > BEHAVIOR_BUDGET:
            logger.debug("llm_retry_behavior_budget", cost=cost, budget=BEHAVIOR_BUDGET)
            breakdown = ", ".join(
                f"{b.action.value}@{b.intensity.value}({compute_behavior_cost(b)})"
                for b in behaviors
            )
            raise ModelRetry(
                f"Behavior budget {cost}/{BEHAVIOR_BUDGET}. Behaviors: {breakdown}. "
                f"Remove behaviors or lower intensity."
            )
        return behaviors


class CreatorOutputSpec(CreatorOutput):
    """A game object with a name, tags, optional behaviors, and visual description."""

    behaviors: list[BehaviorSpec] = Field(default_factory=list, max_length=3)  # type: ignore[assignment]

    @field_validator("behaviors")
    @classmethod
    def check_behavior_budget(cls, behaviors: list[BehaviorSpec]) -> list[BehaviorSpec]:  # type: ignore[override]
        from pydantic_ai import ModelRetry

        if not behaviors:
            return behaviors
        costs = [(b, compute_spec_cost(b)) for b in behaviors]
        total = sum(c for _, c in costs)
        if total > BEHAVIOR_BUDGET:
            logger.debug("llm_retry_behavior_budget", cost=total, budget=BEHAVIOR_BUDGET)
            breakdown = ", ".join(
                f"{b.action.value}@{b.power.value}({c})" for b, c in costs
            )
            raise ModelRetry(
                f"Behavior budget {total}/{BEHAVIOR_BUDGET}. Behaviors: {breakdown}. "
                f"Remove behaviors or lower power."
            )
        return behaviors


class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str
    tags: list[Tag]
    behaviors: list[Behavior] = Field(default_factory=list)
    visual_descriptor: VisualDescriptor

    @computed_field  # type: ignore[prop-decorator]
    @property
    def power_cost(self) -> int:
        return sum(TAG_POWER_COSTS[t] for t in self.tags)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def behavior_cost(self) -> int:
        return sum(compute_behavior_cost(b) for b in self.behaviors)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def starting_durability(self) -> int:
        if Tag.BREAKABLE in self.tags:
            return DURABILITY_BREAKABLE
        if Tag.RIGID in self.tags:
            return DURABILITY_RIGID
        if Tag.FLEXIBLE in self.tags:
            return DURABILITY_FLEXIBLE
        return DURABILITY_DEFAULT
