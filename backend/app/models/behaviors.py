from enum import StrEnum
from typing import Self

from pydantic import BaseModel, model_validator

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


class Power(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- Cost tables ---

BEHAVIOR_BUDGET: int = 8

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


# Actions that always target SELF (client ignores the target field)
_SELF_ONLY_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.SELF_DESTRUCT, BehaviorAction.EXPLODE}
)

# Movement actions that need a real target (target=SELF produces a zero vector)
_DIRECTIONAL_MOVEMENT_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY}
)

# All movement actions (including PATROL which ignores target)
_ALL_MOVEMENT_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY, BehaviorAction.PATROL}
)

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
    intensity: Intensity = Intensity.MEDIUM
    range: BehaviorRange = BehaviorRange.MEDIUM
    speed: Speed = Speed.MEDIUM
    interval: Interval = Interval.MEDIUM
    tags_to_apply: list[Tag] | None = None
    trigger_tag: Tag | None = None

    @model_validator(mode="after")
    def check_trigger_tag(self) -> Self:
        if self.trigger == BehaviorTrigger.ON_TAG_ADDED:
            if self.trigger_tag is None:
                raise ValueError(
                    "ON_TAG_ADDED trigger requires trigger_tag to specify which tag to watch."
                )
        elif self.trigger_tag is not None:
            raise ValueError(
                f"trigger_tag is only valid with ON_TAG_ADDED trigger, not {self.trigger}."
            )
        return self

    @model_validator(mode="after")
    def check_target_compatibility(self) -> Self:
        if (
            self.target == BehaviorTarget.CONTACT_BODY
            and self.trigger not in _CONTACT_BODY_TRIGGERS
        ):
            raise ValueError(
                f"CONTACT_BODY target requires ON_CONTACT, ON_DAMAGED, or ON_PROXIMITY trigger, "
                f"not {self.trigger}."
            )
        return self

    @model_validator(mode="after")
    def check_tags_to_apply(self) -> Self:
        needs_tags = self.action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS}
        if needs_tags and not self.tags_to_apply:
            raise ValueError(
                f"{self.action} action requires tags_to_apply to specify which tags."
            )
        return self

    @model_validator(mode="after")
    def check_action_target(self) -> Self:
        if self.action in _SELF_ONLY_ACTIONS and self.target != BehaviorTarget.SELF:
            raise ValueError(
                f"{self.action} always affects this object. Set target to SELF."
            )
        if self.action in _DIRECTIONAL_MOVEMENT_ACTIONS and self.target == BehaviorTarget.SELF:
            raise ValueError(
                f"{self.action} needs something to move toward/away from. "
                f"Use NEAREST_OBJECT, NEAREST_LIVING, NEAREST_PLAYER, or CONTACT_BODY."
            )
        return self

    @model_validator(mode="after")
    def check_action_trigger(self) -> Self:
        if (
            self.trigger == BehaviorTrigger.ON_DESTROY
            and self.action in _ALL_MOVEMENT_ACTIONS
        ):
            raise ValueError(
                f"{self.action} is useless with ON_DESTROY — the object is being removed. "
                f"Use a non-movement action like EXPLODE or DEAL_DAMAGE instead."
            )
        return self


# ---------------------------------------------------------------------------
# BehaviorSpec — simplified LLM-facing model
# ---------------------------------------------------------------------------

_POWER_TO_INTENSITY: dict[Power, Intensity] = {
    Power.LOW: Intensity.LOW,
    Power.MEDIUM: Intensity.MEDIUM,
    Power.HIGH: Intensity.HIGH,
}

_POWER_TO_SPEED: dict[Power, Speed] = {
    Power.LOW: Speed.SLOW,
    Power.MEDIUM: Speed.MEDIUM,
    Power.HIGH: Speed.FAST,
}

_POWER_TO_RANGE: dict[Power, BehaviorRange] = {
    Power.LOW: BehaviorRange.CLOSE,
    Power.MEDIUM: BehaviorRange.MEDIUM,
    Power.HIGH: BehaviorRange.FAR,
}

_POWER_TO_INTERVAL: dict[Power, Interval] = {
    Power.LOW: Interval.SLOW,
    Power.MEDIUM: Interval.MEDIUM,
    Power.HIGH: Interval.FAST,
}


class BehaviorSpec(BaseModel):
    """Simplified behavior model for LLM output. Expanded to full Behavior after."""

    trigger: BehaviorTrigger
    action: BehaviorAction
    target: BehaviorTarget = BehaviorTarget.NEAREST_OBJECT
    power: Power = Power.MEDIUM
    trigger_tag: Tag | None = None
    tags_to_apply: list[Tag] | None = None

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
    def check_tags_to_apply(self) -> Self:
        from pydantic_ai import ModelRetry

        needs_tags = self.action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS}
        if needs_tags and not self.tags_to_apply:
            raise ModelRetry(
                f"{self.action} action requires tags_to_apply to specify which tags."
            )
        return self


def compute_spec_cost(spec: BehaviorSpec) -> int:
    """Compute behavior cost from a BehaviorSpec (using power instead of intensity)."""
    base = BEHAVIOR_ACTION_COSTS[spec.action]
    modifier = 1 if spec.power == Power.HIGH else 0
    floor = SPAWN_EXPLODE_FLOOR if spec.action in _FLOORED_ACTIONS else 1
    return max(floor, base + modifier)


def expand_behavior_spec(spec: BehaviorSpec) -> Behavior:
    """Expand a simplified BehaviorSpec into a full Behavior with deterministic mappings."""
    target = spec.target
    action = spec.action

    # Deterministic fixes
    if action in _SELF_ONLY_ACTIONS:
        target = BehaviorTarget.SELF
    elif action in _DIRECTIONAL_MOVEMENT_ACTIONS and target == BehaviorTarget.SELF:
        target = BehaviorTarget.NEAREST_OBJECT
    if target == BehaviorTarget.CONTACT_BODY and spec.trigger not in _CONTACT_BODY_TRIGGERS:
        target = BehaviorTarget.NEAREST_OBJECT
    if spec.trigger == BehaviorTrigger.ON_DESTROY and action in _ALL_MOVEMENT_ACTIONS:
        action = BehaviorAction.DEAL_DAMAGE

    # Map power to per-action parameters
    intensity = _POWER_TO_INTENSITY[spec.power]
    speed = _POWER_TO_SPEED[spec.power]
    range_ = _POWER_TO_RANGE[spec.power]
    interval = _POWER_TO_INTERVAL[spec.power]

    return Behavior(
        trigger=spec.trigger,
        action=action,
        target=target,
        intensity=intensity,
        range=range_,
        speed=speed,
        interval=interval,
        tags_to_apply=spec.tags_to_apply,
        trigger_tag=spec.trigger_tag,
    )
