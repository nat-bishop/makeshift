"""Tests for blueprint models: CreatorOutput validation, GameObjectBlueprint."""

import pytest
from app.models.blueprint import (
    BehaviorVerb,
    BehaviorVerbSpec,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.substances import Element, Substance
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
            name="Fire Sword",
            substance=Substance.METAL,
            element=Element.BURNING,
            tags=[Tag.SHARP],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Fire Sword"
        assert out.substance == Substance.METAL
        assert out.element == Element.BURNING
        assert out.tags == [Tag.SHARP]

    def test_no_tags_valid(self) -> None:
        out = CreatorOutput(
            name="Rock",
            substance=Substance.STONE,
            visual_descriptor=_make_visual(),
        )
        assert out.tags == []

    def test_no_element_valid(self) -> None:
        out = CreatorOutput(
            name="Rock",
            substance=Substance.STONE,
            tags=[],
            visual_descriptor=_make_visual(),
        )
        assert out.element is None

    def test_too_many_tags_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Over",
                substance=Substance.METAL,
                tags=[Tag.SHARP, Tag.HEAVY, Tag.LIGHT, Tag.BOUNCY],  # 4 > max 3
                visual_descriptor=_make_visual(),
            )

    def test_invalid_llm_tag_raises(self) -> None:
        """Tags absorbed by substance (RIGID, METALLIC, etc.) should be rejected."""
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Sword",
                substance=Substance.METAL,
                tags=[Tag.RIGID],  # RIGID not in LLM visible set
                visual_descriptor=_make_visual(),
            )

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="The Great Big Sword",
                substance=Substance.METAL,
                tags=[Tag.SHARP],
                visual_descriptor=_make_visual(),
            )

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="",
                substance=Substance.METAL,
                visual_descriptor=_make_visual(),
            )

    def test_name_stripped(self) -> None:
        out = CreatorOutput(
            name="  Fire Sword  ",
            substance=Substance.METAL,
            tags=[Tag.SHARP],
            visual_descriptor=_make_visual(),
        )
        assert out.name == "Fire Sword"

    def test_behaviors_valid(self) -> None:
        out = CreatorOutput(
            name="Cop",
            substance=Substance.FLESH,
            tags=[Tag.LIVING],
            behaviors=[
                BehaviorVerbSpec(verb=BehaviorVerb.EAT, target="donuts"),
                BehaviorVerbSpec(verb=BehaviorVerb.DESTROY, target="criminals"),
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 2

    def test_too_many_behaviors_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Cop",
                substance=Substance.FLESH,
                tags=[Tag.LIVING],
                behaviors=[
                    BehaviorVerbSpec(verb=BehaviorVerb.EAT, target="a"),
                    BehaviorVerbSpec(verb=BehaviorVerb.DESTROY, target="b"),
                    BehaviorVerbSpec(verb=BehaviorVerb.FLEE, target="c"),
                    BehaviorVerbSpec(verb=BehaviorVerb.FOLLOW, target="d"),
                    BehaviorVerbSpec(verb=BehaviorVerb.PROTECT, target="e"),
                ],
                visual_descriptor=_make_visual(),
            )

    def test_dedup_tags(self) -> None:
        out = CreatorOutput(
            name="Rock",
            substance=Substance.STONE,
            tags=[Tag.SHARP, Tag.SHARP],
            visual_descriptor=_make_visual(),
        )
        assert out.tags == [Tag.SHARP]


class TestGameObjectBlueprint:
    def _make_blueprint(self, **kwargs: object) -> GameObjectBlueprint:
        defaults: dict[str, object] = {
            "id": "test-id",
            "name": "Test",
            "description": "A test object",
            "substance": Substance.STONE,
            "tags": [Tag.RIGID, Tag.HEAVY],
            "visual_descriptor": _make_visual(),
            "starting_durability": 300,
        }
        defaults.update(kwargs)
        return GameObjectBlueprint(**defaults)  # type: ignore[arg-type]

    def test_substance_stored(self) -> None:
        bp = self._make_blueprint()
        assert bp.substance == Substance.STONE

    def test_starting_durability(self) -> None:
        bp = self._make_blueprint(starting_durability=250)
        assert bp.starting_durability == 250

    def test_serialization_includes_all_fields(self) -> None:
        bp = self._make_blueprint()
        data = bp.model_dump(mode="json")
        assert "substance" in data
        assert "substance_profile" in data
        assert "combat_profile" in data
        assert "identity_embedding" in data
        assert "compiled_behaviors" in data
        assert "starting_durability" in data
