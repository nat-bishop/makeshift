"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint computed fields."""

import pytest
from app.models.blueprint import (
    DURABILITY_BREAKABLE,
    DURABILITY_DEFAULT,
    DURABILITY_RIGID,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import Tag
from pydantic import ValidationError
from pydantic_ai import ModelRetry


def _make_visual(**kwargs: object) -> VisualDescriptor:
    defaults: dict[str, object] = {
        "visual_description": "a gray stone cube",
        "size_category": "medium",
    }
    defaults.update(kwargs)
    return VisualDescriptor(**defaults)  # type: ignore[arg-type]


class TestVisualDescriptor:
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
            tags=[Tag.RIGID, Tag.HEAVY],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Test Object"
        assert len(out.tags) == 2

    def test_contradiction_raises(self) -> None:
        """Contradictory tags should raise a validation error (ModelRetry in agent context)."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Bad Object",
                tags=[Tag.FROZEN, Tag.MOLTEN],
                visual_descriptor=_make_visual(),
            )

    def test_high_cost_tags_valid_without_budget(self) -> None:
        """Without budget, expensive tag combos should pass if count is valid."""
        out = CreatorOutput(
            name="Expensive",
            tags=[Tag.EXPLOSIVE, Tag.ELECTRIC, Tag.SHARP],
            visual_descriptor=_make_visual(),
        )
        assert len(out.tags) == 3

    def test_multiple_contradictions(self) -> None:
        """RIGID + LIQUID is a contradiction."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.RIGID, Tag.LIQUID],
                visual_descriptor=_make_visual(),
            )

    def test_metallic_insulating_contradiction(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Impossible",
                tags=[Tag.METALLIC, Tag.INSULATING],
                visual_descriptor=_make_visual(),
            )

    def test_single_tag_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Rock",
                tags=[Tag.RIGID],
                visual_descriptor=_make_visual(),
            )

    def test_two_tags_valid(self) -> None:
        out = CreatorOutput(
            name="Rock",
            tags=[Tag.RIGID, Tag.HEAVY],
            visual_descriptor=_make_visual(),
        )
        assert len(out.tags) == 2

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
                    Tag.RIGID,
                    Tag.LIGHT,
                    Tag.COLD,
                    Tag.BREAKABLE,
                    Tag.FLAMMABLE,
                    Tag.WET,
                ],  # 6 tags, over max of 5
                visual_descriptor=_make_visual(),
            )

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="The Great Big Sword",
                tags=[Tag.RIGID, Tag.HEAVY],
                visual_descriptor=_make_visual(),
            )

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="",
                tags=[Tag.RIGID, Tag.HEAVY],
                visual_descriptor=_make_visual(),
            )

    def test_name_stripped(self) -> None:
        out = CreatorOutput(
            name="  Fire Sword  ",
            tags=[Tag.RIGID, Tag.HEAVY],
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
            tags=tags if tags is not None else [Tag.RIGID, Tag.HEAVY],
            visual_descriptor=(
                visual_descriptor if visual_descriptor is not None else _make_visual()
            ),
        )

    def test_durability_breakable(self) -> None:
        bp = self._make_blueprint(tags=[Tag.RIGID, Tag.BREAKABLE])
        assert bp.starting_durability == DURABILITY_BREAKABLE

    def test_durability_rigid(self) -> None:
        bp = self._make_blueprint(tags=[Tag.RIGID, Tag.HEAVY])
        assert bp.starting_durability == DURABILITY_RIGID

    def test_durability_default(self) -> None:
        bp = self._make_blueprint(tags=[Tag.LIQUID, Tag.HEAVY])
        assert bp.starting_durability == DURABILITY_DEFAULT

    def test_durability_breakable_takes_precedence(self) -> None:
        """BREAKABLE check comes first, even if RIGID is also present."""
        bp = self._make_blueprint(tags=[Tag.RIGID, Tag.BREAKABLE])
        assert bp.starting_durability == DURABILITY_BREAKABLE

    def test_serialization_includes_computed_fields(self) -> None:
        bp = self._make_blueprint(tags=[Tag.RIGID, Tag.HEAVY])
        data = bp.model_dump(mode="json")
        assert "starting_durability" in data
