"""Implied behaviors — minimal. The LLM controls behavior directly.

Only one default: CREATURE with empty behaviors → append investigate → "interesting nearby objects".
"""

from app.models.blueprint import BehaviorVerb, BehaviorVerbSpec
from app.models.tags import Category

_DEFAULT_CREATURE_BEHAVIOR = BehaviorVerbSpec(
    verb=BehaviorVerb.INVESTIGATE,
    target_description="interesting nearby objects",
    target_tag="",
)


def resolve_implied_behaviors(
    categories: list[Category],
    explicit_behaviors: list[BehaviorVerbSpec],
) -> list[BehaviorVerbSpec]:
    """If CREATURE and no explicit behaviors, add a default wander."""
    if Category.CREATURE in categories and not explicit_behaviors:
        return [_DEFAULT_CREATURE_BEHAVIOR]
    return list(explicit_behaviors)
