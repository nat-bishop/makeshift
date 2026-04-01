from typing import Literal

import structlog
from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator

from app.models.behaviors import (
    Behavior,
    BehaviorParseError,
    parse_behavior_string,
)
from app.models.tags import (
    LLM_VISIBLE_TAGS,
    TAG_AUTO_CORRECTIONS,
    TAG_CONTRADICTIONS,
    TAG_DESCRIPTIONS,
    Tag,
)

DURABILITY_BREAKABLE = 50
DURABILITY_RIGID = 200
DURABILITY_DEFAULT = 150

logger = structlog.get_logger()

# Pre-computed constants for tag validation (avoid rebuilding per call)
_VALID_TAG_VALUES: frozenset[str] = frozenset(t.value for t in Tag)
_TAG_HELP_STRING: str = "\n".join(
    f"  {tag.value} — {TAG_DESCRIPTIONS[tag]}"
    for tag in sorted(LLM_VISIBLE_TAGS, key=lambda t: t.value)
)


class VisualDescriptor(BaseModel):
    visual_description: str = Field(
        description="1-2 sentences: shape, material, colors, distinctive features"
    )
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = Field(
        description="Scale relative to the player character (small-to-medium sized)"
    )


class CreatorOutput(BaseModel):
    name: str
    tags: list[Tag] = Field(min_length=2, max_length=5)
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
    def auto_correct_tags(cls, tags: list) -> list:
        """Auto-correct removed/renamed tags and reject hallucinated ones."""
        from pydantic_ai import ModelRetry

        corrected = []
        for t in tags:
            if isinstance(t, str):
                upper = t.strip().upper()
                if upper in TAG_AUTO_CORRECTIONS:
                    replacement = TAG_AUTO_CORRECTIONS[upper]
                    logger.debug(
                        "tag_auto_corrected", original=upper, replacement=replacement.value
                    )
                    corrected.append(replacement.value)
                    continue
                if upper not in _VALID_TAG_VALUES:
                    raise ModelRetry(
                        f"Unknown tag '{t}'. Choose from these tags:\n{_TAG_HELP_STRING}"
                    )
            corrected.append(t)
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped = []
        for t in corrected:
            val = t.value if isinstance(t, Tag) else str(t)
            if val not in seen:
                seen.add(val)
                deduped.append(t)
        return deduped

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
    """A game object with a name, tags, optional signature behavior, and visual description."""

    signature: str | None = Field(
        default=None,
        description=(
            "One unique behavior that defines this object. Optional — most objects "
            "don't need one. Format: TRIGGER -> ACTION or TRIGGER -> ACTION -> TARGET, "
            "power=POWER. Parametric: ON_TAG_ADDED(TAG), ADD_TAGS(TAG1, TAG2). "
            "Don't write behaviors that tags already handle (chase, flee, patrol, detonate)."
        ),
    )

    @field_validator("signature")
    @classmethod
    def check_signature(cls, signature: str | None) -> str | None:
        from pydantic_ai import ModelRetry

        if signature is None:
            return None
        try:
            parse_behavior_string(signature)
        except (BehaviorParseError, ValidationError) as e:
            logger.debug("llm_retry_signature_parse", signature=signature, error=str(e))
            raise ModelRetry(
                f"Invalid signature '{signature}': {e}\n"
                f"Expected: TRIGGER -> ACTION or TRIGGER -> ACTION -> TARGET\n"
                f"Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE"
            ) from e
        return signature


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
        return DURABILITY_DEFAULT
