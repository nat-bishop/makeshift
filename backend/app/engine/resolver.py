"""Rule engine: two-tier index (pair O(1) + wildcard O(n)) with priority sorting."""

import structlog

from app.models.rules import InteractionRule
from app.models.tags import Tag

logger = structlog.get_logger()


class RuleResolver:
    """Resolves matching interaction rules for a pair of tag sets."""

    def __init__(self, rules: list[InteractionRule]) -> None:
        self._pair_index: dict[Tag, dict[Tag, list[InteractionRule]]] = {}
        self._wildcard_rules: list[InteractionRule] = []
        self._build_index(rules)
        pair_count = sum(
            len(inner) for outer in self._pair_index.values() for inner in outer.values()
        )
        logger.info(
            "rule_resolver_built",
            total_rules=len(rules),
            pair_entries=pair_count,
            wildcard_rules=len(self._wildcard_rules),
        )

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
                            ):
                                if not (rule.tags_blocked_by and rule.tags_blocked_by & tags_b):
                                    matched[rule.rule_id] = rule
                            elif (
                                rule.bidirectional
                                and rule.tags_required_a <= tags_b
                                and rule.tags_required_b <= tags_a
                            ):
                                if not (rule.tags_blocked_by and rule.tags_blocked_by & tags_a):
                                    matched[rule.rule_id] = rule

        # Wildcard rules - O(n) where n is small (~3-5)
        for rule in self._wildcard_rules:
            if rule.tags_required_a.issubset(tags_a):
                if not (rule.tags_blocked_by and rule.tags_blocked_by & tags_b):
                    matched[rule.rule_id] = rule
            elif rule.bidirectional and rule.tags_required_a.issubset(tags_b):
                if not (rule.tags_blocked_by and rule.tags_blocked_by & tags_a):
                    matched[rule.rule_id] = rule

        result = sorted(matched.values(), key=lambda r: r.priority, reverse=True)
        if result:
            logger.debug(
                "rules_matched",
                match_count=len(result),
                tags_a=sorted(t.value for t in tags_a),
                tags_b=sorted(t.value for t in tags_b),
            )
        return result
