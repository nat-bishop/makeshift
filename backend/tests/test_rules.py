"""Tests for rule engine: resolver indexing, matching, execution_order sorting."""

from app.engine.resolver import RuleResolver
from app.engine.rules_data import ALL_RULES
from app.models.effects import Effect, EffectTarget, EffectType
from app.models.rules import InteractionRule
from app.models.tags import Tag

_DEFAULT_EFFECTS = [
    Effect(
        effect_type=EffectType.DAMAGE,
        target=EffectTarget.B,
        damage_amount=10.0,
        message="Test effect",
    )
]


def _make_rule(
    rule_id: str = "test_rule",
    name: str = "Test Rule",
    tags_required_a: set[Tag] | None = None,
    tags_required_b: set[Tag] | None = None,
    execution_order: int = 10,
    bidirectional: bool = True,
    cascade_eligible: bool = False,
    effects: list[Effect] | None = None,
) -> InteractionRule:
    return InteractionRule(
        rule_id=rule_id,
        name=name,
        tags_required_a=(tags_required_a if tags_required_a is not None else {Tag.HEAT_SOURCE}),
        tags_required_b=(tags_required_b if tags_required_b is not None else {Tag.FLAMMABLE}),
        execution_order=execution_order,
        bidirectional=bidirectional,
        cascade_eligible=cascade_eligible,
        effects=effects if effects is not None else _DEFAULT_EFFECTS,
    )


class TestRuleResolver:
    def test_basic_match(self):
        rule = _make_rule()
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE, Tag.RIGID}, {Tag.FLAMMABLE, Tag.BREAKABLE}
        )
        assert len(matches) == 1
        assert matches[0].rule_id == "test_rule"

    def test_no_match(self):
        rule = _make_rule()
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules({Tag.COLD}, {Tag.RIGID})
        assert len(matches) == 0

    def test_bidirectional_match(self):
        rule = _make_rule(bidirectional=True)
        resolver = RuleResolver([rule])
        # Reversed: b has HEAT_SOURCE, a has FLAMMABLE
        matches = resolver.find_matching_rules(
            {Tag.FLAMMABLE, Tag.RIGID}, {Tag.HEAT_SOURCE, Tag.RIGID}
        )
        assert len(matches) == 1

    def test_non_bidirectional_no_reverse(self):
        rule = _make_rule(bidirectional=False)
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules({Tag.FLAMMABLE}, {Tag.HEAT_SOURCE})
        assert len(matches) == 0

    def test_wildcard_rule(self):
        rule = _make_rule(
            rule_id="sticky_wildcard",
            tags_required_a={Tag.STICKY},
            tags_required_b=set(),
            bidirectional=False,
        )
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules({Tag.STICKY, Tag.RIGID}, {Tag.RIGID, Tag.HEAVY})
        assert len(matches) == 1

    def test_wildcard_no_match_wrong_a(self):
        rule = _make_rule(
            tags_required_a={Tag.STICKY},
            tags_required_b=set(),
            bidirectional=False,
        )
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules({Tag.RIGID}, {Tag.RIGID})
        assert len(matches) == 0

    def test_execution_order_sorting(self):
        low = _make_rule(rule_id="low", execution_order=5)
        high = _make_rule(rule_id="high", execution_order=15)
        resolver = RuleResolver([low, high])
        matches = resolver.find_matching_rules({Tag.HEAT_SOURCE}, {Tag.FLAMMABLE})
        assert len(matches) == 2
        assert matches[0].rule_id == "high"
        assert matches[1].rule_id == "low"

    def test_deduplication(self):
        """Same rule should not appear twice even if multiple tag pairs match."""
        rule = _make_rule(
            tags_required_a={Tag.HEAT_SOURCE},
            tags_required_b={Tag.FLAMMABLE},
        )
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE, Tag.HOT}, {Tag.FLAMMABLE, Tag.BREAKABLE}
        )
        assert len(matches) == 1

    def test_multi_tag_requirement(self):
        """Rule requiring multiple tags in a-set."""
        rule = _make_rule(
            tags_required_a={Tag.HEAT_SOURCE, Tag.SHARP},
            tags_required_b={Tag.FLAMMABLE},
        )
        resolver = RuleResolver([rule])
        # Only HEAT_SOURCE, missing SHARP
        matches = resolver.find_matching_rules({Tag.HEAT_SOURCE}, {Tag.FLAMMABLE})
        assert len(matches) == 0
        # Both present
        matches = resolver.find_matching_rules({Tag.HEAT_SOURCE, Tag.SHARP}, {Tag.FLAMMABLE})
        assert len(matches) == 1


class TestAllRules:
    def test_all_rules_loaded(self):
        assert len(ALL_RULES) == 50

    def test_all_rules_have_unique_ids(self):
        ids = [r.rule_id for r in ALL_RULES]
        assert len(ids) == len(set(ids)), "Duplicate rule IDs found"

    def test_all_rules_have_effects(self):
        for rule in ALL_RULES:
            assert len(rule.effects) > 0, f"Rule {rule.rule_id} has no effects"

    def test_all_rules_have_valid_tags(self):
        for rule in ALL_RULES:
            for tag in rule.tags_required_a:
                assert isinstance(tag, Tag)
            for tag in rule.tags_required_b:
                assert isinstance(tag, Tag)

    def test_resolver_builds_without_error(self):
        resolver = RuleResolver(ALL_RULES)
        assert resolver is not None

    def test_heat_flammable_ignite(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.HEAT_SOURCE}, {Tag.FLAMMABLE})
        rule_ids = [m.rule_id for m in matches]
        assert "heat_flammable_ignite" in rule_ids

    def test_explosive_heat_detonate(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.EXPLOSIVE}, {Tag.HEAT_SOURCE})
        rule_ids = [m.rule_id for m in matches]
        assert "explosive_heat_detonate" in rule_ids

    def test_insulating_blocks_electric(self):
        resolver = RuleResolver(ALL_RULES)
        # INSULATING on B-side should block electric rules
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC}, {Tag.METALLIC, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "electric_metallic_electrify" not in rule_ids

    def test_insulating_blocks_heat(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE}, {Tag.FLAMMABLE, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "heat_flammable_ignite" not in rule_ids

    def test_insulating_blocks_cold(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.COLD}, {Tag.LIQUID, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "cold_liquid_freeze" not in rule_ids

    def test_insulating_blocks_bidirectional_reversed(self):
        resolver = RuleResolver(ALL_RULES)
        # Bidirectional: A has FLAMMABLE+INSULATING, B has HEAT_SOURCE
        # Rule flips to match, blocking should still apply
        matches = resolver.find_matching_rules(
            {Tag.FLAMMABLE, Tag.INSULATING}, {Tag.HEAT_SOURCE}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "heat_flammable_ignite" not in rule_ids

    def test_insulating_does_not_block_unrelated(self):
        resolver = RuleResolver(ALL_RULES)
        # INSULATING should not block non-electric/heat/cold rules
        matches = resolver.find_matching_rules(
            {Tag.ACIDIC}, {Tag.BREAKABLE, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "acidic_breakable_corrode" in rule_ids

    def test_electric_flammable_spark(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.ELECTRIC}, {Tag.FLAMMABLE})
        rule_ids = [m.rule_id for m in matches]
        assert "electric_flammable_spark" in rule_ids

    def test_electric_flammable_spark_bidirectional(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.FLAMMABLE}, {Tag.ELECTRIC})
        rule_ids = [m.rule_id for m in matches]
        assert "electric_flammable_spark" in rule_ids

    def test_electric_flammable_spark_blocked_by_insulating(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC}, {Tag.FLAMMABLE, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "electric_flammable_spark" not in rule_ids

    def test_electric_gas_ionize(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.ELECTRIC}, {Tag.GAS})
        rule_ids = [m.rule_id for m in matches]
        assert "electric_gas_ionize" in rule_ids

    def test_electric_gas_ionize_bidirectional(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.GAS}, {Tag.ELECTRIC})
        rule_ids = [m.rule_id for m in matches]
        assert "electric_gas_ionize" in rule_ids

    def test_electric_gas_ionize_blocked_by_insulating(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC}, {Tag.GAS, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "electric_gas_ionize" not in rule_ids

    def test_electric_flammable_breakable_both_fire(self):
        """ELECTRIC + FLAMMABLE+BREAKABLE target: both spark and damage rules fire."""
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC}, {Tag.FLAMMABLE, Tag.BREAKABLE}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "electric_flammable_spark" in rule_ids
        assert "electric_breakable_damage" in rule_ids

    def test_electric_flammable_spark_priority_below_ignition(self):
        """Spark ignition (p9) should fire after main ignition (p10)."""
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC, Tag.HEAT_SOURCE}, {Tag.FLAMMABLE}
        )
        rule_ids = [m.rule_id for m in matches]
        assert rule_ids.index("heat_flammable_ignite") < rule_ids.index(
            "electric_flammable_spark"
        )

    def test_hostile_hostile_clash(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.HOSTILE}, {Tag.HOSTILE})
        rule_ids = [m.rule_id for m in matches]
        assert "hostile_hostile_clash" in rule_ids

    def test_hostile_has_knockback(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.HOSTILE}, {Tag.LIVING})
        rule = next(m for m in matches if m.rule_id == "hostile_living_damage")
        effect_types = [e.effect_type for e in rule.effects]
        assert EffectType.APPLY_FORCE in effect_types

    def test_reflective_acidic_resist(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.REFLECTIVE}, {Tag.ACIDIC})
        rule_ids = [m.rule_id for m in matches]
        assert "reflective_acidic_resist" in rule_ids

    def test_liquid_wet_spread(self):
        """LIQUID wildcard rule should match against any tags_b."""
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.LIQUID}, {Tag.RIGID, Tag.HEAVY})
        rule_ids = [m.rule_id for m in matches]
        assert "liquid_wet_spread" in rule_ids

    def test_wet_electric_amplify(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.WET}, {Tag.ELECTRIC})
        rule_ids = [m.rule_id for m in matches]
        assert "wet_electric_amplify" in rule_ids

    def test_wet_electric_blocked_by_insulating(self):
        resolver = RuleResolver(ALL_RULES)
        # INSULATING on the ELECTRIC side (B) blocks the wet_electric_amplify rule
        matches = resolver.find_matching_rules(
            {Tag.WET}, {Tag.ELECTRIC, Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "wet_electric_amplify" not in rule_ids

    def test_wet_cold_freeze(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.WET}, {Tag.COLD})
        rule_ids = [m.rule_id for m in matches]
        assert "wet_cold_freeze" in rule_ids

    def test_heat_wet_dry(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules({Tag.HEAT_SOURCE}, {Tag.WET})
        rule_ids = [m.rule_id for m in matches]
        assert "heat_wet_dry" in rule_ids

    def test_wet_blocks_ignition(self):
        """WET should block heat_flammable_ignite (wet things resist fire)."""
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE}, {Tag.FLAMMABLE, Tag.WET}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "heat_flammable_ignite" not in rule_ids
