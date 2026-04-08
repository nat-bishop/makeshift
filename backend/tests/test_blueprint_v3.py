"""Tests for V3 blueprint models."""

import pytest
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)
from pydantic import ValidationError


class TestPhysicsProperties:
    def test_damping_derivation(self):
        p = PhysicsProperties(mass_kg=1.5, height_cm=120, friction=30, bounce=10, gravity=50)
        # damping = 120 / (1.5 * 100 + 10) = 120 / 160 = 0.75
        assert abs(p.damping - 0.75) < 0.01

    def test_damping_light_large(self):
        """Feather: high damping (floaty)."""
        p = PhysicsProperties(mass_kg=0.01, height_cm=20, friction=10, bounce=5, gravity=40)
        # 20 / (0.01 * 100 + 10) = 20 / 11 = 1.82
        assert p.damping > 1.5

    def test_damping_heavy_small(self):
        """Bullet: low damping."""
        p = PhysicsProperties(mass_kg=10.0, height_cm=5, friction=30, bounce=10, gravity=60)
        # 5 / (10 * 100 + 10) = 5 / 1010 = 0.005
        assert p.damping < 0.01

    def test_size_category_tiny(self):
        p = PhysicsProperties(mass_kg=0.01, height_cm=5, friction=0, bounce=0, gravity=5)
        assert p.size_category == "tiny"

    def test_size_category_small(self):
        p = PhysicsProperties(mass_kg=0.5, height_cm=30, friction=50, bounce=10, gravity=50)
        assert p.size_category == "small"

    def test_size_category_medium(self):
        p = PhysicsProperties(mass_kg=1.5, height_cm=120, friction=30, bounce=10, gravity=50)
        assert p.size_category == "medium"

    def test_size_category_large(self):
        p = PhysicsProperties(mass_kg=70.0, height_cm=170, friction=50, bounce=10, gravity=50)
        assert p.size_category == "large"

    def test_size_category_huge(self):
        p = PhysicsProperties(mass_kg=5000.0, height_cm=800, friction=50, bounce=10, gravity=50)
        assert p.size_category == "huge"

    def test_mass_range_clamped(self):
        with pytest.raises(ValidationError):
            PhysicsProperties(mass_kg=0.0, height_cm=30, friction=50, bounce=10, gravity=50)

    def test_friction_range(self):
        with pytest.raises(ValidationError):
            PhysicsProperties(mass_kg=1.0, height_cm=30, friction=101, bounce=10, gravity=50)


class TestGameObjectBlueprint:
    def test_valid_blueprint(self):
        bp = GameObjectBlueprint(
            id="test-1",
            name="fire sword",
            description="a fiery sword",
            visual_description="a longsword wreathed in orange flames",
            physics=PhysicsProperties(
                mass_kg=1.5, height_cm=120, friction=30, bounce=10, gravity=50
            ),
            destructibility=Destructibility(armor=80, hp=90, indestructible=False),
            affordance=0,
            autonomous=False,
        )
        assert bp.name == "fire sword"
        assert bp.affordance == 0
        assert bp.physics.size_category == "medium"

    def test_name_validation_empty(self):
        with pytest.raises(ValidationError, match="empty"):
            GameObjectBlueprint(
                id="t", name="", description="x",
                visual_description="x",
                physics=PhysicsProperties(
                    mass_kg=1, height_cm=30, friction=50, bounce=10, gravity=50,
                ),
                destructibility=Destructibility(),
            )

    def test_name_validation_too_long(self):
        with pytest.raises(ValidationError, match="3 words"):
            GameObjectBlueprint(
                id="t", name="a very long name indeed", description="x",
                visual_description="x",
                physics=PhysicsProperties(
                    mass_kg=1, height_cm=30, friction=50, bounce=10, gravity=50,
                ),
                destructibility=Destructibility(),
            )

    def test_affordance_range(self):
        with pytest.raises(ValidationError):
            GameObjectBlueprint(
                id="t", name="x", description="x", visual_description="x",
                physics=PhysicsProperties(
                    mass_kg=1, height_cm=30, friction=50, bounce=10, gravity=50,
                ),
                destructibility=Destructibility(),
                affordance=5,
            )

    def test_serialization_roundtrip(self):
        bp = GameObjectBlueprint(
            id="rt-1", name="rock", description="rock",
            visual_description="a grey boulder",
            physics=PhysicsProperties(mass_kg=50, height_cm=60, friction=60, bounce=5, gravity=65),
            destructibility=Destructibility(armor=70, hp=80),
            affordance=3, autonomous=False,
        )
        json_str = bp.model_dump_json()
        restored = GameObjectBlueprint.model_validate_json(json_str)
        assert restored.name == "rock"
        assert restored.physics.mass_kg == 50.0
        assert restored.destructibility.armor == 70
