"""Generate context strings for LLM judge rubrics.

Builds tag lists and rule summaries from the actual game data
so rubrics stay in sync with the codebase.
"""

from __future__ import annotations

from app.engine.rules_data import ALL_RULES
from app.models.tags import LLM_VISIBLE_TAGS_V2, Tag

_V2_TAG_NAMES = sorted(t.value for t in LLM_VISIBLE_TAGS_V2)

# All tags that can appear at runtime (LLM-visible + substance/element-derived + internal)
_ALL_RUNTIME_TAGS = frozenset(Tag)

# Rules involving any runtime tags (not just LLM-visible — rules fire on derived traits too)
_VISIBLE_RULES = [
    rule
    for rule in ALL_RULES
    if all(t in _ALL_RUNTIME_TAGS for t in rule.tags_required_a)
    and (not rule.tags_required_b or all(t in _ALL_RUNTIME_TAGS for t in rule.tags_required_b))
]


def get_tag_list_string() -> str:
    """Comma-separated list of V2 LLM-visible Tag values."""
    return ", ".join(_V2_TAG_NAMES)


def get_rules_summary_string() -> str:
    """One-liner per rule: 'Name: TAG_A + TAG_B (bidirectional)'."""
    lines: list[str] = []
    for rule in _VISIBLE_RULES:
        tags_a = " + ".join(t.value for t in rule.tags_required_a)
        tags_b = " + ".join(t.value for t in rule.tags_required_b) or "(any)"
        direction = "bidirectional" if rule.bidirectional else "one-way"
        lines.append(f"- {rule.name}: {tags_a} + {tags_b} ({direction})")
    return "\n".join(lines)


def get_visible_rule_count() -> int:
    """Number of rules visible to the LLM judge."""
    return len(_VISIBLE_RULES)
