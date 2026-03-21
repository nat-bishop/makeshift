"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint computed fields."""

import pytest
from app.models.blueprint import CreatorOutput, GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag
from pydantic_ai import ModelRetry


def _make_visual(
    base_form: str = "cube",
    material: str = "stone",
    color_primary: str = "#888888",
    color_secondary: str = "#666666",
    visual_effects: list[str] | None = None,
    size_category: str = "medium",
) -> VisualDescriptor:
    return VisualDescriptor(
        base_form=base_form,
        material=material,
        color_primary=color_primary,
        color_secondary=color_secondary,
        visual_effects=visual_effects if visual_effects is not None else [],
        size_category=size_category,
    )


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
                visual_descriptor if visual_descriptor is not None
                else _make_visual()
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
        assert bp.starting_durability == 50

    def test_durability_rigid(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.starting_durability == 200

    def test_durability_flexible(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.FLEXIBLE])
        assert bp.starting_durability == 100

    def test_durability_default(self) -> None:
        bp = self._make_blueprint(tags=[Tag.LIQUID, Tag.HEAVY])
        assert bp.starting_durability == 150

    def test_durability_breakable_takes_precedence(self) -> None:
        """BREAKABLE check comes first, even if RIGID is also present."""
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.BREAKABLE])
        assert bp.starting_durability == 50

    def test_serialization_includes_computed_fields(self) -> None:
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.TOOL])
        data = bp.model_dump(mode="json")
        assert "power_cost" in data
        assert "is_equippable" in data
        assert "equip_slot" in data
        assert "equip_tags" in data
        assert "starting_durability" in data
