"""Implied behaviors — minimal. The LLM controls behavior directly.

Only one default: LIVING with empty behaviors → append investigate → "interesting nearby objects".
"""

from app.models.blueprint import BehaviorVerb, BehaviorVerbSpec
from app.models.tags import Tag

_DEFAULT_LIVING_BEHAVIOR = BehaviorVerbSpec(
    verb=BehaviorVerb.INVESTIGATE,
    target="interesting nearby objects",
)


def resolve_implied_behaviors(
    tags: list[Tag],
    explicit_behaviors: list[BehaviorVerbSpec],
) -> list[BehaviorVerbSpec]:
    """If LIVING and no explicit behaviors, add a default wander."""
    if Tag.LIVING in tags and not explicit_behaviors:
        return [_DEFAULT_LIVING_BEHAVIOR]
    return list(explicit_behaviors)
