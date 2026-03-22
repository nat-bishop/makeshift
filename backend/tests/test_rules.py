"""Tests for rule engine: resolver indexing, matching, priority sorting."""

from app.engine.resolver import RuleResolver
from app.engine.rules_data import ALL_RULES
from app.models.effects import Effect, EffectTarget, EffectType
from app.models.rules import InteractionRule
from app.models.tags import Tag

_DEFAULT_EFFECTS = [
    Effect(
        effect_type=EffectType.IGNITE,
        target=EffectTarget.B,
        message="Test effect",
    )
]


def _make_rule(
    rule_id: str = "test_rule",
    name: str = "Test Rule",
    tags_required_a: set[Tag] | None = None,
    tags_required_b: set[Tag] | None = None,
    priority: int = 10,
    bidirectional: bool = True,
    cascade_eligible: bool = False,
    effects: list[Effect] | None = None,
) -> InteractionRule:
    return InteractionRule(
        rule_id=rule_id,
        name=name,
        tags_required_a=(
            tags_required_a if tags_required_a is not None
            else {Tag.HEAT_SOURCE}
        ),
        tags_required_b=(
            tags_required_b if tags_required_b is not None
            else {Tag.FLAMMABLE}
        ),
        priority=priority,
        bidirectional=bidirectional,
        cascade_eligible=cascade_eligible,
        effects=effects if effects is not None else _DEFAULT_EFFECTS,
    )


class TestRuleResolver:
    def test_basic_match(self):
        rule = _make_rule()
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE, Tag.SOLID}, {Tag.FLAMMABLE, Tag.BREAKABLE}
        )
        assert len(matches) == 1
        assert matches[0].rule_id == "test_rule"

    def test_no_match(self):
        rule = _make_rule()
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.COLD}, {Tag.RIGID}
        )
        assert len(matches) == 0

    def test_bidirectional_match(self):
        rule = _make_rule(bidirectional=True)
        resolver = RuleResolver([rule])
        # Reversed: b has HEAT_SOURCE, a has FLAMMABLE
        matches = resolver.find_matching_rules(
            {Tag.FLAMMABLE, Tag.SOLID}, {Tag.HEAT_SOURCE, Tag.RIGID}
        )
        assert len(matches) == 1

    def test_non_bidirectional_no_reverse(self):
        rule = _make_rule(bidirectional=False)
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.FLAMMABLE}, {Tag.HEAT_SOURCE}
        )
        assert len(matches) == 0

    def test_wildcard_rule(self):
        rule = _make_rule(
            rule_id="sticky_wildcard",
            tags_required_a={Tag.STICKY},
            tags_required_b=set(),
            bidirectional=False,
        )
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.STICKY, Tag.SOLID}, {Tag.RIGID, Tag.HEAVY}
        )
        assert len(matches) == 1

    def test_wildcard_no_match_wrong_a(self):
        rule = _make_rule(
            tags_required_a={Tag.STICKY},
            tags_required_b=set(),
            bidirectional=False,
        )
        resolver = RuleResolver([rule])
        matches = resolver.find_matching_rules(
            {Tag.SOLID}, {Tag.RIGID}
        )
        assert len(matches) == 0

    def test_priority_sorting(self):
        low = _make_rule(rule_id="low", priority=5)
        high = _make_rule(rule_id="high", priority=15)
        resolver = RuleResolver([low, high])
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE}, {Tag.FLAMMABLE}
        )
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
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE}, {Tag.FLAMMABLE}
        )
        assert len(matches) == 0
        # Both present
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE, Tag.SHARP}, {Tag.FLAMMABLE}
        )
        assert len(matches) == 1


class TestAllRules:
    def test_all_rules_loaded(self):
        assert len(ALL_RULES) >= 50

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
        matches = resolver.find_matching_rules(
            {Tag.HEAT_SOURCE}, {Tag.FLAMMABLE}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "heat_flammable_ignite" in rule_ids

    def test_explosive_heat_detonate(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.EXPLOSIVE}, {Tag.HEAT_SOURCE}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "explosive_heat_detonate" in rule_ids

    def test_electric_insulating_block(self):
        resolver = RuleResolver(ALL_RULES)
        matches = resolver.find_matching_rules(
            {Tag.ELECTRIC}, {Tag.INSULATING}
        )
        rule_ids = [m.rule_id for m in matches]
        assert "electric_insulating_block" in rule_ids
        # Should be highest priority among matches
        assert matches[0].rule_id == "electric_insulating_block"
