"""Rule engine: two-tier index (pair O(1) + wildcard O(n)) with priority sorting."""

from app.models.rules import InteractionRule
from app.models.tags import Tag


class RuleResolver:
    """Resolves matching interaction rules for a pair of tag sets."""

    def __init__(self, rules: list[InteractionRule]) -> None:
        self._pair_index: dict[Tag, dict[Tag, list[InteractionRule]]] = {}
        self._wildcard_rules: list[InteractionRule] = []
        self._build_index(rules)

    def _build_index(self, rules: list[InteractionRule]) -> None:
        for rule in rules:
            if not rule.tags_required_b:  # wildcard rule
                self._wildcard_rules.append(rule)
            else:
                for ta in rule.tags_required_a:
                    for tb in rule.tags_required_b:
                        (self._pair_index.setdefault(ta, {}).setdefault(tb, []).append(rule))
                        if rule.bidirectional:
                            (self._pair_index.setdefault(tb, {}).setdefault(ta, []).append(rule))

    def find_matching_rules(self, tags_a: set[Tag], tags_b: set[Tag]) -> list[InteractionRule]:
        """Find all rules matching the two tag sets, sorted by priority descending."""
        matched: dict[str, InteractionRule] = {}

        # Pair index lookup - O(|tags_a| * |tags_b|) with O(1) per pair
        for ta in tags_a:
            if ta in self._pair_index:
                for tb in tags_b:
                    if tb in self._pair_index[ta]:
                        for rule in self._pair_index[ta][tb]:
                            if (
                                rule.tags_required_a <= tags_a and rule.tags_required_b <= tags_b
                            ) or (
                                rule.bidirectional
                                and rule.tags_required_a <= tags_b
                                and rule.tags_required_b <= tags_a
                            ):
                                matched[rule.rule_id] = rule

        # Wildcard rules - O(n) where n is small (~3-5)
        for rule in self._wildcard_rules:
            if rule.tags_required_a.issubset(tags_a) or (
                rule.bidirectional and rule.tags_required_a.issubset(tags_b)
            ):
                matched[rule.rule_id] = rule

        return sorted(matched.values(), key=lambda r: r.priority, reverse=True)
