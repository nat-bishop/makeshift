"""Tests for the Effect model: construction, defaults, enum completeness, serialization."""

import pytest
from app.models.effects import Effect, EffectTarget, EffectType
from app.models.tags import Tag


class TestEffectTypeEnum:
    def test_member_count(self):
        assert len(EffectType) == 5

    @pytest.mark.parametrize(
        "member, expected_value",
        [
            (EffectType.DAMAGE, "DAMAGE"),
            (EffectType.HEAL, "HEAL"),
            (EffectType.ADD_TAG, "ADD_TAG"),
            (EffectType.REMOVE_TAG, "REMOVE_TAG"),
            (EffectType.APPLY_FORCE, "APPLY_FORCE"),
        ],
    )
    def test_str_values(self, member: EffectType, expected_value: str):
        assert member.value == expected_value
        assert str(member) == expected_value


class TestEffectTargetEnum:
    def test_member_count(self):
        assert len(EffectTarget) == 3

    @pytest.mark.parametrize(
        "member, expected_value",
        [
            (EffectTarget.A, "a"),
            (EffectTarget.B, "b"),
            (EffectTarget.BOTH, "both"),
        ],
    )
    def test_str_values(self, member: EffectTarget, expected_value: str):
        assert member.value == expected_value
        assert str(member) == expected_value


class TestEffectConstruction:
    def test_damage_effect(self):
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target=EffectTarget.B,
            damage_amount=25.0,
            message="burned",
        )
        assert effect.effect_type == EffectType.DAMAGE
        assert effect.target == EffectTarget.B
        assert effect.damage_amount == 25.0
        assert effect.message == "burned"

    def test_heal_effect(self):
        effect = Effect(
            effect_type=EffectType.HEAL,
            target=EffectTarget.A,
            damage_amount=10.0,
        )
        assert effect.effect_type == EffectType.HEAL
        assert effect.damage_amount == 10.0

    def test_add_tag_effect(self):
        effect = Effect(
            effect_type=EffectType.ADD_TAG,
            target=EffectTarget.B,
            tag=Tag.FROZEN,
            tag_duration=5.0,
        )
        assert effect.tag == Tag.FROZEN
        assert effect.tag_duration == 5.0

    def test_remove_tag_effect(self):
        effect = Effect(
            effect_type=EffectType.REMOVE_TAG,
            target=EffectTarget.B,
            tag=Tag.FLAMMABLE,
        )
        assert effect.tag == Tag.FLAMMABLE

    def test_apply_force_effect(self):
        effect = Effect(
            effect_type=EffectType.APPLY_FORCE,
            target=EffectTarget.BOTH,
            force_magnitude=500.0,
        )
        assert effect.force_magnitude == 500.0

    def test_dot_effect(self):
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target=EffectTarget.B,
            damage_amount=5.0,
            tick_interval=1.0,
            tick_duration=10.0,
        )
        assert effect.tick_interval == 1.0
        assert effect.tick_duration == 10.0


class TestEffectDefaults:
    def test_message_defaults_to_empty_string(self):
        effect = Effect(effect_type=EffectType.DAMAGE, target=EffectTarget.B)
        assert effect.message == ""

    def test_optional_fields_default_to_none(self):
        effect = Effect(effect_type=EffectType.DAMAGE, target=EffectTarget.B)
        assert effect.damage_amount is None
        assert effect.tick_interval is None
        assert effect.tick_duration is None
        assert effect.tag is None
        assert effect.tag_duration is None
        assert effect.force_magnitude is None

    def test_damage_without_tag_is_valid(self):
        """Model does NOT enforce semantic field requirements -- DAMAGE doesn't need tag."""
        effect = Effect(
            effect_type=EffectType.DAMAGE,
            target=EffectTarget.B,
            damage_amount=10.0,
        )
        assert effect.tag is None

    def test_add_tag_without_damage_amount_is_valid(self):
        """Model does NOT enforce semantic field requirements -- ADD_TAG doesn't need damage_amount."""
        effect = Effect(
            effect_type=EffectType.ADD_TAG,
            target=EffectTarget.B,
            tag=Tag.FROZEN,
        )
        assert effect.damage_amount is None
