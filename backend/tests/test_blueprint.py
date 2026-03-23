"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint computed fields."""

import pytest
from app.models.blueprint import (
    DURABILITY_BREAKABLE,
    DURABILITY_DEFAULT,
    DURABILITY_FLEXIBLE,
    DURABILITY_RIGID,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import TAG_POWER_COSTS, Tag
from pydantic import ValidationError
from pydantic_ai import ModelRetry

def _make_visual(**kwargs: object) -> VisualDescriptor:
    defaults: dict[str, object] = {
        "base_form": "cube",
        "material": "stone",
        "color_primary": "#888888",
        "color_primary_name": "gray",
        "color_secondary": "#666666",
        "color_secondary_name": "dark gray",
        "visual_effects": [],
        "size_category": "medium",
        "bg_color": "#4A6741",
    }
    defaults.update(kwargs)
    return VisualDescriptor(**defaults)


class TestVisualDescriptor:
    def test_valid_hex_colors(self) -> None:
        vd = _make_visual(color_primary="#FF4444", color_secondary="#222222")
        assert vd.color_primary == "#FF4444"

    @pytest.mark.parametrize(
        "bad_color",
        ["red", "#FFF", "FF4444", "#ZZZZZZ", ""],
    )
    def test_invalid_color_primary_raises(self, bad_color: str) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_primary=bad_color)

    @pytest.mark.parametrize(
        "bad_color",
        ["blue", "#000", "666666"],
    )
    def test_invalid_color_secondary_raises(self, bad_color: str) -> None:
        with pytest.raises(ValidationError):
            _make_visual(color_secondary=bad_color)

    def test_empty_visual_effects(self) -> None:
        """Empty visual_effects list is valid."""
        vd = _make_visual(visual_effects=[])
        assert vd.visual_effects == []

    def test_valid_size_categories(self) -> None:
        for size in ("tiny", "small", "medium", "large", "huge"):
            vd = _make_visual(size_category=size)
            assert vd.size_category == size

    def test_invalid_size_category_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_visual(size_category="gigantic")


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

    def test_exact_budget_high_cost_tags(self) -> None:
        """Tags totaling exactly OBJECT_TAG_BUDGET (10) should pass."""
        # EXPLOSIVE(5) + MOLTEN(4) + BREAKABLE(1) = 10
        co = CreatorOutput(
            name="Lava Bomb",
            tags=[Tag.EXPLOSIVE, Tag.MOLTEN, Tag.BREAKABLE],
            visual_descriptor=_make_visual(),
        )
        assert sum(TAG_POWER_COSTS[t] for t in co.tags) == 10


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
        bp = self._make_blueprint(tags=[Tag.SOLID, Tag.RIGID])
        data = bp.model_dump(mode="json")
        assert "power_cost" in data
        assert "starting_durability" in data
