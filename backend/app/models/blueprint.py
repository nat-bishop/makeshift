from typing import Literal

import structlog
from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator

from app.models.behaviors import (
    Behavior,
    BehaviorParseError,
    parse_behavior_string,
)
from app.models.tags import (
    TAG_CONTRADICTIONS,
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



class CreatorOutputSpec(CreatorOutput):
    """A game object with a name, tags, behaviors, and visual description."""

    behaviors: list[str] = Field(  # type: ignore[assignment]
        max_length=3,
        description=(
            "Behavior notation: TRIGGER -> ACTION -> TARGET, power=POWER. "
            "Parametric: ON_TAG_ADDED(TAG), ADD_TAGS(TAG1, TAG2). "
            "Example: ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=high"
        ),
    )

    @field_validator("behaviors")
    @classmethod
    def check_behaviors(cls, behaviors: list[str]) -> list[str]:
        from pydantic_ai import ModelRetry

        if not behaviors:
            return behaviors
        for s in behaviors:
            try:
                parse_behavior_string(s)
            except (BehaviorParseError, ValidationError) as e:
                logger.debug("llm_retry_behavior_parse", behavior=s, error=str(e))
                raise ModelRetry(
                    f"Invalid behavior '{s}': {e}\n"
                    f"Expected: TRIGGER -> ACTION -> TARGET\n"
                    f"Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high"
                ) from e
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
    def starting_durability(self) -> int:
        if Tag.BREAKABLE in self.tags:
            return DURABILITY_BREAKABLE
        if Tag.RIGID in self.tags:
            return DURABILITY_RIGID
        if Tag.FLEXIBLE in self.tags:
            return DURABILITY_FLEXIBLE
        return DURABILITY_DEFAULT
