
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.tags import (
    EQUIP_SLOT_MAP,
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    TRANSFERABLE_TAGS,
    Tag,
)

DURABILITY_BREAKABLE = 50
DURABILITY_RIGID = 200
DURABILITY_FLEXIBLE = 100
DURABILITY_DEFAULT = 150


class VisualDescriptor(BaseModel):
    base_form: str
    material: str
    color_primary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    color_secondary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    visual_effects: list[str]
    size_category: Literal["tiny", "small", "medium", "large", "huge"]


class CreatorOutput(BaseModel):
    name: str
    tags: list[Tag] = Field(min_length=2, max_length=6)
    visual_descriptor: VisualDescriptor

    @field_validator("name")
    @classmethod
    def check_name_length(cls, name: str) -> str:
        from pydantic_ai import ModelRetry

        name = name.strip()
        if not name:
            raise ModelRetry("Name cannot be empty.")
        words = name.split()
        if len(words) > 3:
            raise ModelRetry(
                f'Name "{name}" has {len(words)} words. Use 1-3 words maximum.'
            )
        return name

    @field_validator("tags")
    @classmethod
    def check_contradictions(cls, tags: list[Tag]) -> list[Tag]:
        from pydantic_ai import ModelRetry

        tag_set = set(tags)
        for pair in TAG_CONTRADICTIONS:
            if pair <= tag_set:
                a, b = sorted(pair, key=lambda t: t.value)
                raise ModelRetry(f"{a.value} and {b.value} cannot coexist. Remove one.")
        return tags

    @field_validator("tags")
    @classmethod
    def check_budget(cls, tags: list[Tag]) -> list[Tag]:
        from pydantic_ai import ModelRetry

        cost = sum(TAG_POWER_COSTS[t] for t in tags)
        if cost > OBJECT_TAG_BUDGET:
            breakdown = ", ".join(f"{t.value}({TAG_POWER_COSTS[t]})" for t in tags)
            raise ModelRetry(
                f"Budget {cost}/{OBJECT_TAG_BUDGET}. Tags: {breakdown}. Remove expensive tags."
            )
        return tags


class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str
    tags: list[Tag]
    visual_descriptor: VisualDescriptor

    @computed_field  # type: ignore[prop-decorator]
    @property
    def power_cost(self) -> int:
        return sum(TAG_POWER_COSTS[t] for t in self.tags)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_equippable(self) -> bool:
        return bool({Tag.WEARABLE, Tag.TOOL} & set(self.tags))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def equip_slot(self) -> str | None:
        if not self.is_equippable:
            return None
        return EQUIP_SLOT_MAP.get(self.visual_descriptor.base_form, "hand")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def equip_tags(self) -> list[Tag]:
        return [t for t in self.tags if t in TRANSFERABLE_TAGS]

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
