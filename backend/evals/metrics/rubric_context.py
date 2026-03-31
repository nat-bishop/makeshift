"""Generate context strings for LLM judge rubrics.

Builds tag lists and rule summaries from the actual game data
so rubrics stay in sync with the codebase.
"""

from __future__ import annotations

from app.engine.rules_data import ALL_RULES
from app.models.tags import Tag

_ALL_TAG_NAMES = [t.value for t in Tag]


def get_tag_list_string() -> str:
    """Comma-separated list of all valid Tag enum values."""
    return ", ".join(_ALL_TAG_NAMES)


def get_rules_summary_string() -> str:
    """One-liner per rule: 'Name: TAG_A + TAG_B (bidirectional)'."""
    lines: list[str] = []
    for rule in ALL_RULES:
        tags_a = " + ".join(t.value for t in rule.tags_required_a)
        tags_b = " + ".join(t.value for t in rule.tags_required_b) or "(any)"
        direction = "bidirectional" if rule.bidirectional else "one-way"
        lines.append(f"- {rule.name}: {tags_a} + {tags_b} ({direction})")
    return "\n".join(lines)
