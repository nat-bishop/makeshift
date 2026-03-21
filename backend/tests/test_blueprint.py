"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint computed fields."""

import pytest

from app.models.blueprint import CreatorOutput, GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag


def _make_visual(**overrides) -> VisualDescriptor:
    defaults = dict(
        base_form="cube",
        material="stone",
        color_primary="#888888",
        color_secondary="#666666",
        visual_effects=[],
        size_category="medium",
    )
    defaults.update(overrides)
    return VisualDescriptor(**defaults)


class TestCreatorOutput:
    def test_valid_creation(self):
        out = CreatorOutput(
            name="Test Object",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Test Object"
        assert len(out.tags) == 2

    def test_contradiction_raises(self):
        """Contradictory tags should raise a validation error (ModelRetry in agent context)."""
        with pytest.raises(Exception):
            CreatorOutput(
                name="Bad Object",
                tags=[Tag.FROZEN, Tag.HOT],
                visual_descriptor=_make_visual(),
            )

    def test_budget_exceeded_raises(self):
        """Tags exceeding budget=10 should raise."""
        with pytest.raises(Exception):
            CreatorOutput(
                name="Expensive",
                tags=[Tag.EXPLOSIVE, Tag.ELECTRIC, Tag.SHARP],  # 5+4+2=11
                visual_descriptor=_make_visual(),
            )

    def test_budget_exactly_10_valid(self):
        # SOLID(1) + RIGID(1) + HEAT_SOURCE(3) + HOT(2) + GLOWING(2) + LIGHT(1) = 10
        out = CreatorOutput(
            name="Torch",
            tags=[Tag.SOLID, Tag.RIGID, Tag.HEAT_SOURCE, Tag.HOT, Tag.GLOWING, Tag.LIGHT],
            visual_descriptor=_make_visual(),
        )
        assert len(out.tags) == 6

    def test_multiple_contradictions(self):
        """SOLID + LIQUID is a contradiction."""
        with pytest.raises(Exception):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.SOLID, Tag.LIQUID],
                visual_descriptor=_make_visual(),
            )

    def test_sticky_slippery_contradiction(self):
        with pytest.raises(Exception):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.STICKY, Tag.SLIPPERY],
                visual_descriptor=_make_visual(),
            )


class TestGameObjectBlueprint:
    def _make_blueprint(self, **overrides) -> GameObjectBlueprint:
        defaults = dict(
            id="test-id",
            name="Test",
            description="A test object",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        defaults.update(overrides)
        return GameObjectBlueprint(**defaults)

    def test_power_cost(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.SHARP])
        assert bp.power_cost == 4  # 1+1+2

    def test_is_equippable_with_tool(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.TOOL])
        assert bp.is_equippable is True

    def test_is_equippable_with_wearable(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.WEARABLE])
        assert bp.is_equippable is True

    def test_not_equippable(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.is_equippable is False

    def test_equip_slot_sword(self):
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.TOOL],
            visual_descriptor=_make_visual(base_form="sword"),
        )
        assert bp.equip_slot == "hand"

    def test_equip_slot_shield(self):
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.WEARABLE],
            visual_descriptor=_make_visual(base_form="shield"),
        )
        assert bp.equip_slot == "back"

    def test_equip_slot_helmet(self):
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.WEARABLE],
            visual_descriptor=_make_visual(base_form="helmet"),
        )
        assert bp.equip_slot == "head"

    def test_equip_slot_default_hand(self):
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.TOOL],
            visual_descriptor=_make_visual(base_form="unknown_form"),
        )
        assert bp.equip_slot == "hand"

    def test_equip_slot_none_when_not_equippable(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.equip_slot is None

    def test_equip_tags(self):
        bp = self._make_blueprint(
            tags=[Tag.SOLID, Tag.RIGID, Tag.HEAT_SOURCE, Tag.SHARP, Tag.TOOL],
        )
        assert Tag.HEAT_SOURCE in bp.equip_tags
        assert Tag.SHARP in bp.equip_tags
        assert Tag.SOLID not in bp.equip_tags
        assert Tag.RIGID not in bp.equip_tags

    def test_durability_breakable(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.BREAKABLE])
        assert bp.starting_durability == 50

    def test_durability_rigid(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        assert bp.starting_durability == 200

    def test_durability_flexible(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.FLEXIBLE])
        assert bp.starting_durability == 100

    def test_durability_default(self):
        bp = self._make_blueprint(tags=[Tag.LIQUID, Tag.HEAVY])
        assert bp.starting_durability == 150

    def test_durability_breakable_takes_precedence(self):
        """BREAKABLE check comes first, even if RIGID is also present."""
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.BREAKABLE])
        assert bp.starting_durability == 50

    def test_serialization_includes_computed_fields(self):
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID, Tag.TOOL])
        data = bp.model_dump(mode="json")
        assert "power_cost" in data
        assert "is_equippable" in data
        assert "equip_slot" in data
        assert "equip_tags" in data
        assert "starting_durability" in data
