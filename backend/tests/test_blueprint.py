"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint computed fields."""

import pytest
from typing import Literal

from app.models.blueprint import (
    DURABILITY_BREAKABLE,
    DURABILITY_DEFAULT,
    DURABILITY_FLEXIBLE,
    DURABILITY_RIGID,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import Tag
from pydantic import ValidationError
from pydantic_ai import ModelRetry

SizeCategory = Literal["tiny", "small", "medium", "large", "huge"]


def _make_visual(
    base_form: str = "cube",
    material: str = "stone",
    color_primary: str = "#888888",
    color_primary_name: str = "gray",
    color_secondary: str = "#666666",
    color_secondary_name: str = "dark gray",
    visual_effects: list[str] | None = None,
    size_category: SizeCategory = "medium",
    bg_color: str = "#808080",
) -> VisualDescriptor:
    return VisualDescriptor(
        base_form=base_form,
        material=material,
        color_primary=color_primary,
        color_primary_name=color_primary_name,
        color_secondary=color_secondary,
        color_secondary_name=color_secondary_name,
        visual_effects=visual_effects if visual_effects is not None else [],
        size_category=size_category,
        bg_color=bg_color,
    )


class TestVisualDescriptor:
    def test_valid_hex_colors(self) -> None:
        vd = _make_visual(color_primary="#FF4444", color_secondary="#222222")
        assert vd.color_primary == "#FF4444"

    def test_invalid_color_primary_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_primary="red")

    def test_invalid_color_secondary_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_secondary="blue")

    def test_short_hex_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_primary="#FFF")

    def test_missing_hash_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_primary="FF4444")

    def test_valid_size_categories(self) -> None:
        for size in ("tiny", "small", "medium", "large", "huge"):
            vd = _make_visual(size_category=size)
            assert vd.size_category == size

    def test_invalid_size_category_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(size_category="gigantic")  # type: ignore[arg-type]


class TestCreatorOutput:
    def test_valid_creation(self) -> None:
        out = CreatorOutput(
            name="Test Object",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Test Object"
        assert len(out.tags) == 2

    def test_contradiction_raises(self) -> None:
        """Contradictory tags should raise a validation error (ModelRetry in agent context)."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Bad Object",
                tags=[Tag.FROZEN, Tag.HOT],
                visual_descriptor=_make_visual(),
            )

    def test_budget_exceeded_raises(self) -> None:
        """Tags exceeding budget=10 should raise."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Expensive",
                tags=[Tag.EXPLOSIVE, Tag.ELECTRIC, Tag.SHARP],  # 5+4+2=11
                visual_descriptor=_make_visual(),
            )

    def test_budget_exactly_10_valid(self) -> None:
        # SOLID(1) + RIGID(1) + HEAT_SOURCE(3) + HOT(2) + GLOWING(2) + LIGHT(1) = 10
        out = CreatorOutput(
            name="Torch",
            tags=[Tag.SOLID, Tag.RIGID, Tag.HEAT_SOURCE, Tag.HOT, Tag.GLOWING, Tag.LIGHT],
            visual_descriptor=_make_visual(),
        )
        assert len(out.tags) == 6

    def test_multiple_contradictions(self) -> None:
        """SOLID + LIQUID is a contradiction."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.SOLID, Tag.LIQUID],
                visual_descriptor=_make_visual(),
            )

    def test_sticky_slippery_contradiction(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.STICKY, Tag.SLIPPERY],
                visual_descriptor=_make_visual(),
            )

    def test_too_few_tags_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Lonely",
                tags=[Tag.SOLID],
                visual_descriptor=_make_visual(),
            )

    def test_empty_tags_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Empty",
                tags=[],
                visual_descriptor=_make_visual(),
            )

    def test_too_many_tags_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Overloaded",
                tags=[
                    Tag.SOLID,
                    Tag.RIGID,
                    Tag.LIGHT,
                    Tag.COLD,
                    Tag.SLIPPERY,
                    Tag.BREAKABLE,
                    Tag.FLAMMABLE,
                ],  # 7 tags, all cost 1, under budget but over count
                visual_descriptor=_make_visual(),
            )

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="The Great Big Sword",
                tags=[Tag.SOLID, Tag.RIGID],
                visual_descriptor=_make_visual(),
            )

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="",
                tags=[Tag.SOLID, Tag.RIGID],
                visual_descriptor=_make_visual(),
            )

    def test_name_stripped(self) -> None:
        out = CreatorOutput(
            name="  Fire Sword  ",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Fire Sword"


class TestGameObjectBlueprint:
    def _make_blueprint(
        self,
        id: str = "test-id",
        name: str = "Test",
        description: str = "A test object",
        tags: list[Tag] | None = None,
        visual_descriptor: VisualDescriptor | None = None,
    ) -> GameObjectBlueprint:
        return GameObjectBlueprint(
            id=id,
            name=name,
            description=description,
            tags=tags if tags is not None else [Tag.SOLID, Tag.RIGID],
            visual_descriptor=(
                visual_descriptor if visual_descriptor is not None else _make_visual()
            ),
        )

    def test_power_cost(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.SHARP])
        assert bp.power_cost == 4  # 1+1+2

    def test_is_equippable_with_tool(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.TOOL])
        assert bp.is_equippable is True

    def test_is_equippable_with_wearable(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.WEARABLE])
        assert bp.is_equippable is True

    def test_not_equippable(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.is_equippable is False

    def test_equip_slot_sword(self) -> None:
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.TOOL],
            visual_descriptor=_make_visual(base_form="sword"),
        )
        assert bp.equip_slot == "hand"

    def test_equip_slot_shield(self) -> None:
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.WEARABLE],
            visual_descriptor=_make_visual(base_form="shield"),
        )
        assert bp.equip_slot == "back"

    def test_equip_slot_helmet(self) -> None:
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.WEARABLE],
            visual_descriptor=_make_visual(base_form="helmet"),
        )
        assert bp.equip_slot == "head"

    def test_equip_slot_default_hand(self) -> None:
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.TOOL],
            visual_descriptor=_make_visual(base_form="unknown_form"),
        )
        assert bp.equip_slot == "hand"

    def test_equip_slot_none_when_not_equippable(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.equip_slot is None

    def test_equip_tags(self) -> None:
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.RIGID, Tag.HEAT_SOURCE, Tag.SHARP, Tag.TOOL],
        )
        assert Tag.HEAT_SOURCE in bp.equip_tags
        assert Tag.SHARP in bp.equip_tags
        assert Tag.SOLID not in bp.equip_tags
        assert Tag.RIGID not in bp.equip_tags

    def test_durability_breakable(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.BREAKABLE])
        assert bp.starting_durability == DURABILITY_BREAKABLE

    def test_durability_rigid(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.starting_durability == DURABILITY_RIGID

    def test_durability_flexible(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.FLEXIBLE])
        assert bp.starting_durability == DURABILITY_FLEXIBLE

    def test_durability_default(self) -> None:
        bp = self._make_blueprint(tags=[Tag.LIQUID, Tag.HEAVY])
        assert bp.starting_durability == DURABILITY_DEFAULT

    def test_durability_breakable_takes_precedence(self) -> None:
        """BREAKABLE check comes first, even if RIGID is also present."""
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.BREAKABLE])
        assert bp.starting_durability == DURABILITY_BREAKABLE

    def test_serialization_includes_computed_fields(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.TOOL])
        data = bp.model_dump(mode="json")
        assert "power_cost" in data
        assert "is_equippable" in data
        assert "equip_slot" in data
        assert "equip_tags" in data
        assert "starting_durability" in data
