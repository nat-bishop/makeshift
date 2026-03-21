from __future__ import annotations

from app.models.rules import InteractionRule
from app.models.tags import Tag


class RuleResolver:
    """Two-tier rule index: pair index (O(1)) + wildcard list (O(n))."""

    def __init__(self, rules: list[InteractionRule]) -> None:
        self._pair_index: dict[Tag, dict[Tag, list[InteractionRule]]] = {}
        self._wildcard_rules: list[InteractionRule] = []
        self._build_index(rules)

    def _build_index(self, rules: list[InteractionRule]) -> None:
        for rule in rules:
            if not rule.tags_required_b:
                # Wildcard rule: matches any b
                self._wildcard_rules.append(rule)
                continue

            # Index by each tag_a → tag_b pair
            for tag_a in rule.tags_required_a:
                if tag_a not in self._pair_index:
                    self._pair_index[tag_a] = {}
                for tag_b in rule.tags_required_b:
                    if tag_b not in self._pair_index[tag_a]:
                        self._pair_index[tag_a][tag_b] = []
                    self._pair_index[tag_a][tag_b].append(rule)

                # If bidirectional, also index b → a
                if rule.bidirectional:
                    for tag_b in rule.tags_required_b:
                        if tag_b not in self._pair_index:
                            self._pair_index[tag_b] = {}
                        if tag_a not in self._pair_index[tag_b]:
                            self._pair_index[tag_b][tag_a] = []
                        self._pair_index[tag_b][tag_a].append(rule)

    def find_matching_rules(
        self, tags_a: list[Tag], tags_b: list[Tag]
    ) -> list[InteractionRule]:
        matched: dict[str, InteractionRule] = {}
        set_a = set(tags_a)
        set_b = set(tags_b)

        # Pair lookup
        for ta in tags_a:
            if ta in self._pair_index:
                for tb in tags_b:
                    if tb in self._pair_index[ta]:
                        for rule in self._pair_index[ta][tb]:
                            fwd = (
                                rule.tags_required_a <= set_a
                                and rule.tags_required_b <= set_b
                            )
                            rev = (
                                rule.bidirectional
                                and rule.tags_required_a <= set_b
                                and rule.tags_required_b <= set_a
                            )
                            if fwd or rev:
                                matched[rule.rule_id] = rule

        # Wildcard rules
        for rule in self._wildcard_rules:
            if rule.tags_required_a <= set_a or (
                rule.bidirectional
                and rule.tags_required_a <= set_b
            ):
                matched[rule.rule_id] = rule

        # Sort by priority descending
        result = list(matched.values())
        result.sort(key=lambda r: r.priority, reverse=True)
        return result
