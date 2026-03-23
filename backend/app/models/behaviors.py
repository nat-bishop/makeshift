from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.tags import Tag


class BehaviorTrigger(StrEnum):
    ALWAYS = "ALWAYS"
    ON_TIMER = "ON_TIMER"
    ON_PROXIMITY = "ON_PROXIMITY"
    ON_CONTACT = "ON_CONTACT"
    ON_DAMAGED = "ON_DAMAGED"
    ON_HEALTH_LOW = "ON_HEALTH_LOW"
    ON_TAG_ADDED = "ON_TAG_ADDED"
    ON_CREATE = "ON_CREATE"
    ON_DESTROY = "ON_DESTROY"
    ON_USE = "ON_USE"


class BehaviorAction(StrEnum):
    MOVE_TOWARD = "MOVE_TOWARD"
    MOVE_AWAY = "MOVE_AWAY"
    PATROL = "PATROL"
    DEAL_DAMAGE = "DEAL_DAMAGE"
    APPLY_FORCE = "APPLY_FORCE"
    ATTRACT = "ATTRACT"
    SPAWN_PROJECTILE = "SPAWN_PROJECTILE"
    EXPLODE = "EXPLODE"
    HEAL = "HEAL"
    ADD_TAGS = "ADD_TAGS"
    REMOVE_TAGS = "REMOVE_TAGS"
    SELF_DESTRUCT = "SELF_DESTRUCT"


class BehaviorTarget(StrEnum):
    SELF = "SELF"
    NEAREST_OBJECT = "NEAREST_OBJECT"
    NEAREST_LIVING = "NEAREST_LIVING"
    NEAREST_PLAYER = "NEAREST_PLAYER"
    CONTACT_BODY = "CONTACT_BODY"


class Intensity(StrEnum):
    MINIMAL = "MINIMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class BehaviorRange(StrEnum):
    TOUCH = "TOUCH"
    CLOSE = "CLOSE"
    MEDIUM = "MEDIUM"
    FAR = "FAR"


class Speed(StrEnum):
    SLOW = "SLOW"
    MEDIUM = "MEDIUM"
    FAST = "FAST"
    VERY_FAST = "VERY_FAST"


class Interval(StrEnum):
    ONCE_SHORT = "ONCE_SHORT"
    ONCE_MEDIUM = "ONCE_MEDIUM"
    ONCE_LONG = "ONCE_LONG"
    SLOW = "SLOW"
    MEDIUM = "MEDIUM"
    FAST = "FAST"


class BehaviorConditionType(StrEnum):
    HAS_TAG = "has_tag"
    NOT_HAS_TAG = "not_has_tag"
    TARGET_HAS_TAG = "target_has_tag"


class BehaviorCondition(BaseModel):
    condition_type: BehaviorConditionType
    tag: Tag


# --- Cost tables ---

BEHAVIOR_BUDGET: int = 6

BEHAVIOR_ACTION_COSTS: dict[BehaviorAction, int] = {
    BehaviorAction.SELF_DESTRUCT: 1,
    BehaviorAction.MOVE_TOWARD: 2,
    BehaviorAction.MOVE_AWAY: 2,
    BehaviorAction.PATROL: 2,
    BehaviorAction.DEAL_DAMAGE: 2,
    BehaviorAction.APPLY_FORCE: 2,
    BehaviorAction.ATTRACT: 2,
    BehaviorAction.HEAL: 2,
    BehaviorAction.ADD_TAGS: 2,
    BehaviorAction.REMOVE_TAGS: 2,
    BehaviorAction.SPAWN_PROJECTILE: 3,
    BehaviorAction.EXPLODE: 3,
}

INTENSITY_COST_MODIFIER: dict[Intensity, int] = {
    Intensity.MINIMAL: -1,
    Intensity.LOW: 0,
    Intensity.MEDIUM: 0,
    Intensity.HIGH: 1,
    Intensity.EXTREME: 2,
}

# Spawn/explode can never cost less than this
SPAWN_EXPLODE_FLOOR: int = 2

_FLOORED_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.SPAWN_PROJECTILE, BehaviorAction.EXPLODE}
)


def compute_behavior_cost(behavior: "Behavior") -> int:
    base = BEHAVIOR_ACTION_COSTS[behavior.action]
    modifier = INTENSITY_COST_MODIFIER[behavior.intensity]
    floor = SPAWN_EXPLODE_FLOOR if behavior.action in _FLOORED_ACTIONS else 1
    return max(floor, base + modifier)


# Triggers that support CONTACT_BODY target
_CONTACT_BODY_TRIGGERS: frozenset[BehaviorTrigger] = frozenset(
    {
        BehaviorTrigger.ON_CONTACT,
        BehaviorTrigger.ON_DAMAGED,
        BehaviorTrigger.ON_PROXIMITY,
    }
)


class Behavior(BaseModel):
    trigger: BehaviorTrigger
    action: BehaviorAction
    target: BehaviorTarget = BehaviorTarget.SELF
    condition: BehaviorCondition | None = None
    intensity: Intensity = Intensity.MEDIUM
    range: BehaviorRange = BehaviorRange.MEDIUM
    speed: Speed = Speed.MEDIUM
    interval: Interval = Interval.MEDIUM
    message: str | None = Field(default=None, max_length=60)
    tags_to_apply: list[Tag] | None = None
    trigger_tag: Tag | None = None

    @model_validator(mode="after")
    def check_trigger_tag(self) -> Self:
        from pydantic_ai import ModelRetry

        if self.trigger == BehaviorTrigger.ON_TAG_ADDED:
            if self.trigger_tag is None:
                raise ModelRetry(
                    "ON_TAG_ADDED trigger requires trigger_tag to specify which tag to watch."
                )
        elif self.trigger_tag is not None:
            raise ModelRetry(
                f"trigger_tag is only valid with ON_TAG_ADDED trigger, not {self.trigger}."
            )
        return self

    @model_validator(mode="after")
    def check_target_compatibility(self) -> Self:
        from pydantic_ai import ModelRetry

        if (
            self.target == BehaviorTarget.CONTACT_BODY
            and self.trigger not in _CONTACT_BODY_TRIGGERS
        ):
            raise ModelRetry(
                f"CONTACT_BODY target requires ON_CONTACT, ON_DAMAGED, or ON_PROXIMITY trigger, "
                f"not {self.trigger}."
            )
        return self

    @model_validator(mode="after")
    def check_tags_to_apply(self) -> Self:
        from pydantic_ai import ModelRetry

        needs_tags = self.action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS}
        if needs_tags and not self.tags_to_apply:
            raise ModelRetry(
                f"{self.action} action requires tags_to_apply to specify which tags."
            )
        return self
