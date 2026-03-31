"""Deep structural validation and uncovered interaction pairs for rules_data.py."""

from app.engine.resolver import RuleResolver
from app.engine.rules_data import ALL_RULES
from app.models.effects import EffectTarget, EffectType
from app.models.rules import TriggerMode
from app.models.tags import Tag


class TestRulesStructuralValidation:
    def test_every_rule_has_valid_trigger_mode(self):
        for rule in ALL_RULES:
            assert rule.trigger_mode in (TriggerMode.CONTACT, TriggerMode.FIELD), (
                f"Rule {rule.rule_id} has invalid trigger_mode: {rule.trigger_mode}"
            )

    def test_every_tags_blocked_by_contains_valid_tags(self):
        for rule in ALL_RULES:
            for tag in rule.tags_blocked_by:
                assert isinstance(tag, Tag), (
                    f"Rule {rule.rule_id} has invalid blocked tag: {tag}"
                )

    def test_every_effect_has_valid_types(self):
        for rule in ALL_RULES:
            for effect in rule.effects:
                assert isinstance(effect.effect_type, EffectType), (
                    f"Rule {rule.rule_id} has invalid effect_type: {effect.effect_type}"
                )
                assert isinstance(effect.target, EffectTarget), (
                    f"Rule {rule.rule_id} has invalid effect target: {effect.target}"
                )

    def test_no_rule_has_empty_tags_required_a(self):
        for rule in ALL_RULES:
            assert len(rule.tags_required_a) > 0, (
                f"Rule {rule.rule_id} has empty tags_required_a"
            )

    def test_cascade_eligible_propagation_rules_add_tags(self):
        """Cascade rules that propagate (not explosive destruction) should add tags."""
        # Explosive rules cascade via destruction/force, not tag propagation.
        explosive_cascade_ids = {
            "explosive_heat_detonate",
            "explosive_breakable_destroy",
            "explosive_electric_detonate",
        }
        for rule in ALL_RULES:
            if rule.cascade_eligible and rule.rule_id not in explosive_cascade_ids:
                has_add_tag = any(
                    e.effect_type == EffectType.ADD_TAG for e in rule.effects
                )
                assert has_add_tag, (
                    f"Non-explosive cascade rule {rule.rule_id} has no ADD_TAG effect"
                )

    def test_field_rules_have_field_trigger_mode(self):
        """Rules marked FIELD in the data should actually have TriggerMode.FIELD."""
        expected_field_ids = {
            "heat_flammable_ignite",
            "heat_frozen_melt",
            "liquid_heat_extinguish",
            "cold_liquid_freeze",
            "electric_metallic_electrify",
            "electric_liquid_electrify",
            "wind_light_push",
            "wind_gas_disperse",
            "magnetic_metallic_attract",
            "toxic_living_damage",
            "cold_molten_freeze",
            "magnetic_magnetic_attract",
            "wind_floating_launch",
            "hot_living_burn",
            "heat_metallic_transfer",
            "cold_metallic_transfer",
            "toxic_gas_cloud",
            "glowing_flammable_smolder",
            "glowing_living_attract",
            "sticky_slow",
            "sticky_living_struggle",
        }
        rule_map = {r.rule_id: r for r in ALL_RULES}
        for rule_id in expected_field_ids:
            assert rule_id in rule_map, f"Expected field rule {rule_id} not found"
            assert rule_map[rule_id].trigger_mode == TriggerMode.FIELD, (
                f"Rule {rule_id} should be FIELD but is {rule_map[rule_id].trigger_mode}"
            )

    def test_all_rules_have_names(self):
        for rule in ALL_RULES:
            assert rule.name.strip(), f"Rule {rule.rule_id} has empty name"

    def test_all_rules_have_positive_execution_order(self):
        for rule in ALL_RULES:
            assert rule.execution_order > 0, (
                f"Rule {rule.rule_id} has non-positive execution_order: {rule.execution_order}"
            )


class TestUncoveredInteractions:
    resolver = RuleResolver(ALL_RULES)

    def _assert_rule_matches(
        self, tags_a: set[Tag], tags_b: set[Tag], expected_rule_id: str
    ) -> None:
        matches = self.resolver.find_matching_rules(tags_a, tags_b)
        rule_ids = [m.rule_id for m in matches]
        assert expected_rule_id in rule_ids, (
            f"Expected {expected_rule_id} in matches for {tags_a} vs {tags_b}, got {rule_ids}"
        )

    def test_wind_light_push(self):
        self._assert_rule_matches({Tag.WIND_SOURCE}, {Tag.LIGHT}, "wind_light_push")

    def test_toxic_living_damage(self):
        self._assert_rule_matches({Tag.TOXIC}, {Tag.LIVING}, "toxic_living_damage")

    def test_magnetic_metallic_attract(self):
        self._assert_rule_matches(
            {Tag.MAGNETIC}, {Tag.METALLIC}, "magnetic_metallic_attract"
        )

    def test_sharp_living_cut(self):
        self._assert_rule_matches({Tag.SHARP}, {Tag.LIVING}, "sharp_living_cut")

    def test_heavy_breakable_crush(self):
        self._assert_rule_matches({Tag.HEAVY}, {Tag.BREAKABLE}, "heavy_breakable_crush")

    def test_reflective_heat_reflect(self):
        self._assert_rule_matches(
            {Tag.REFLECTIVE}, {Tag.HEAT_SOURCE}, "reflective_heat_reflect"
        )

    def test_frozen_breakable_shatter(self):
        self._assert_rule_matches({Tag.FROZEN}, {Tag.BREAKABLE}, "frozen_breakable_shatter")

    def test_molten_flammable_ignite(self):
        self._assert_rule_matches({Tag.MOLTEN}, {Tag.FLAMMABLE}, "molten_flammable_ignite")

    def test_acidic_rigid_weaken(self):
        self._assert_rule_matches({Tag.ACIDIC}, {Tag.RIGID}, "acidic_rigid_weaken")

    def test_bouncy_rigid_extrabounce(self):
        self._assert_rule_matches({Tag.BOUNCY}, {Tag.RIGID}, "bouncy_rigid_extrabounce")

    def test_heat_liquid_evaporate(self):
        self._assert_rule_matches({Tag.HEAT_SOURCE}, {Tag.LIQUID}, "heat_liquid_evaporate")

    def test_heat_metallic_transfer(self):
        self._assert_rule_matches(
            {Tag.HEAT_SOURCE}, {Tag.METALLIC}, "heat_metallic_transfer"
        )

    def test_cold_metallic_transfer(self):
        self._assert_rule_matches({Tag.COLD}, {Tag.METALLIC}, "cold_metallic_transfer")

    def test_explosive_electric_detonate(self):
        self._assert_rule_matches(
            {Tag.EXPLOSIVE}, {Tag.ELECTRIC}, "explosive_electric_detonate"
        )

    # --- BRITTLE rules ---
    def test_brittle_heavy_shatter(self):
        self._assert_rule_matches({Tag.BRITTLE}, {Tag.HEAVY}, "brittle_heavy_shatter")

    def test_brittle_sharp_crack(self):
        self._assert_rule_matches({Tag.BRITTLE}, {Tag.SHARP}, "brittle_sharp_crack")

    # --- CORRODED rules ---
    def test_corroded_heavy_crush(self):
        self._assert_rule_matches({Tag.CORRODED}, {Tag.HEAVY}, "corroded_heavy_crush")

    def test_corroded_sharp_slice(self):
        self._assert_rule_matches({Tag.CORRODED}, {Tag.SHARP}, "corroded_sharp_slice")

    # --- GLOWING rules ---
    def test_glowing_flammable_smolder(self):
        self._assert_rule_matches(
            {Tag.GLOWING}, {Tag.FLAMMABLE}, "glowing_flammable_smolder"
        )

    def test_glowing_living_attract(self):
        self._assert_rule_matches({Tag.GLOWING}, {Tag.LIVING}, "glowing_living_attract")

    # --- STICKY rules ---
    def test_sticky_slow_wildcard(self):
        self._assert_rule_matches({Tag.STICKY}, {Tag.RIGID, Tag.HEAVY}, "sticky_slow")

    def test_sticky_living_struggle(self):
        self._assert_rule_matches({Tag.STICKY}, {Tag.LIVING}, "sticky_living_struggle")

    def test_sticky_heat_fuel(self):
        self._assert_rule_matches(
            {Tag.STICKY}, {Tag.HEAT_SOURCE}, "sticky_heat_fuel"
        )
