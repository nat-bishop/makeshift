
from pydantic import BaseModel, computed_field, field_validator

from app.models.tags import (
    EQUIP_SLOT_MAP,
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    TRANSFERABLE_TAGS,
    Tag,
)


class VisualDescriptor(BaseModel):
    base_form: str
    material: str
    color_primary: str
    color_secondary: str
    visual_effects: list[str]
    size_category: str  # tiny | small | medium | large | huge


class CreatorOutput(BaseModel):
    name: str
    tags: list[Tag]
    visual_descriptor: VisualDescriptor

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
            return 50
        if Tag.RIGID in self.tags:
            return 200
        if Tag.FLEXIBLE in self.tags:
            return 100
        return 150
