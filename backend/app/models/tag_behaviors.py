"""Tag-implied behaviors — common behavior patterns derived from tag combinations.

Tag-implied behaviors are automatically granted to objects based on their tags.
They don't count against the behavior budget. The LLM's explicit "signature"
behavior can override an implied one by sharing the same trigger.

Conflict resolution is per-trigger: if the explicit behavior has the same trigger
as an implied one, the explicit wins that trigger slot. All other implied
behaviors with different triggers survive.
"""

from app.models.behaviors import (
    Behavior,
    BehaviorAction,
    BehaviorRange,
    BehaviorTarget,
    BehaviorTrigger,
    Intensity,
    Interval,
    Speed,
)
from app.models.tags import Tag

# Each entry: (required_tags, excluded_tags, behaviors)
# required_tags: all must be present
# excluded_tags: none may be present (prevents double-application)
_IMPLIED_BEHAVIOR_RULES: list[
    tuple[frozenset[Tag], frozenset[Tag], list[Behavior]]
] = [
    # HOSTILE + LIVING → chase nearest living + flee when hurt
    (
        frozenset({Tag.HOSTILE, Tag.LIVING}),
        frozenset(),
        [
            Behavior(
                trigger=BehaviorTrigger.ALWAYS,
                action=BehaviorAction.MOVE_TOWARD,
                target=BehaviorTarget.NEAREST_LIVING,
                speed=Speed.MEDIUM,
                intensity=Intensity.MEDIUM,
                range=BehaviorRange.MEDIUM,
                interval=Interval.MEDIUM,
                implied=True,
            ),
            Behavior(
                trigger=BehaviorTrigger.ON_HEALTH_LOW,
                action=BehaviorAction.MOVE_AWAY,
                target=BehaviorTarget.NEAREST_LIVING,
                speed=Speed.FAST,
                intensity=Intensity.HIGH,
                range=BehaviorRange.FAR,
                interval=Interval.FAST,
                implied=True,
            ),
        ],
    ),
    # LIVING (no HOSTILE) → gentle wander
    (
        frozenset({Tag.LIVING}),
        frozenset({Tag.HOSTILE}),
        [
            Behavior(
                trigger=BehaviorTrigger.ALWAYS,
                action=BehaviorAction.PATROL,
                target=BehaviorTarget.SELF,
                speed=Speed.SLOW,
                intensity=Intensity.LOW,
                range=BehaviorRange.CLOSE,
                interval=Interval.SLOW,
                implied=True,
            ),
        ],
    ),
    # EXPLOSIVE → detonate when damaged
    (
        frozenset({Tag.EXPLOSIVE}),
        frozenset(),
        [
            Behavior(
                trigger=BehaviorTrigger.ON_DAMAGED,
                action=BehaviorAction.EXPLODE,
                target=BehaviorTarget.SELF,
                intensity=Intensity.HIGH,
                range=BehaviorRange.MEDIUM,
                speed=Speed.FAST,
                interval=Interval.FAST,
                implied=True,
            ),
        ],
    ),
]


def resolve_implied_behaviors(
    tags: list[Tag],
    explicit_behavior: Behavior | None = None,
) -> list[Behavior]:
    """Merge tag-implied behaviors with an optional explicit signature behavior.

    Override is per-trigger: if the explicit behavior shares a trigger with an
    implied behavior, the explicit one replaces that single implied behavior.
    All other implied behaviors with different triggers survive.

    Returns the merged list ordered: implied behaviors first, then explicit.
    """
    tag_set = frozenset(tags)

    # Collect all implied behaviors matching this object's tags
    implied: dict[str, Behavior] = {}
    for required, excluded, behaviors in _IMPLIED_BEHAVIOR_RULES:
        if required <= tag_set and not (excluded & tag_set):
            for b in behaviors:
                # First match for each trigger wins (more-specific rules first)
                if b.trigger not in implied:
                    implied[b.trigger] = b

    # Explicit behavior overrides any implied behavior with the same trigger
    if explicit_behavior is not None:
        implied[explicit_behavior.trigger] = explicit_behavior

    return list(implied.values())
