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


# ---------------------------------------------------------------------------
# Shared validation helpers — used by both Behavior (ValueError) and
# BehaviorSpec (ModelRetry) so the constraint logic lives in one place.
# ---------------------------------------------------------------------------


def _check_trigger_tag(trigger: BehaviorTrigger, trigger_tag: Tag | None) -> str | None:
    if trigger == BehaviorTrigger.ON_TAG_ADDED:
        if trigger_tag is None:
            return "ON_TAG_ADDED trigger requires trigger_tag to specify which tag to watch."
    elif trigger_tag is not None:
        return f"trigger_tag is only valid with ON_TAG_ADDED trigger, not {trigger}."
    return None


def _check_tags_to_apply(action: BehaviorAction, tags_to_apply: list[Tag] | None) -> str | None:
    if action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS} and not tags_to_apply:
        return f"{action} action requires tags_to_apply to specify which tags."
    return None


def _check_self_only_action(action: BehaviorAction, target: BehaviorTarget) -> str | None:
    if action in _SELF_ONLY_ACTIONS and target != BehaviorTarget.SELF:
        return f"{action} always affects this object. target must be SELF."
    return None


def _check_movement_target(action: BehaviorAction, target: BehaviorTarget) -> str | None:
    if action in _DIRECTIONAL_MOVEMENT_ACTIONS and target == BehaviorTarget.SELF:
        return (
            f"{action} needs a target to move toward/away from. "
            f"SELF is not valid. "
            f"Use NEAREST_OBJECT, NEAREST_LIVING, NEAREST_PLAYER, or CONTACT_BODY."
        )
    return None


def _check_contact_body_trigger(
    trigger: BehaviorTrigger, target: BehaviorTarget
) -> str | None:
    if target == BehaviorTarget.CONTACT_BODY and trigger not in _CONTACT_BODY_TRIGGERS:
        return (
            f"CONTACT_BODY target requires ON_CONTACT, ON_DAMAGED, or ON_PROXIMITY "
            f"trigger, not {trigger}."
        )
    return None


def _check_destroy_movement(trigger: BehaviorTrigger, action: BehaviorAction) -> str | None:
    if trigger == BehaviorTrigger.ON_DESTROY and action in _ALL_MOVEMENT_ACTIONS:
        return (
            f"ON_DESTROY cannot use movement actions ({action}). "
            f"The object is being removed from the game."
        )
    return None


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
        if msg := _check_trigger_tag(self.trigger, self.trigger_tag):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_target_compatibility(self) -> Self:
        if msg := _check_contact_body_trigger(self.trigger, self.target):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_tags_to_apply(self) -> Self:
        if msg := _check_tags_to_apply(self.action, self.tags_to_apply):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_action_target(self) -> Self:
        if msg := _check_self_only_action(self.action, self.target):
            raise ValueError(msg)
        if msg := _check_movement_target(self.action, self.target):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_action_trigger(self) -> Self:
        if msg := _check_destroy_movement(self.trigger, self.action):
            raise ValueError(msg)
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

    trigger: BehaviorTrigger = Field(description="When this behavior fires")
    action: BehaviorAction = Field(description="What this behavior does")
    target: BehaviorTarget = Field(
        default=BehaviorTarget.NEAREST_OBJECT,
        description="What the action affects",
    )
    power: Power = Field(
        default=Power.MEDIUM,
        description="Strength/speed/range. 'high' adds +1 to action cost",
    )
    trigger_tag: Tag | None = Field(
        default=None,
        description="Required with ON_TAG_ADDED trigger: which tag to watch for",
    )
    tags_to_apply: list[Tag] | None = Field(
        default=None,
        description="Required with ADD_TAGS/REMOVE_TAGS actions: which tags to add/remove",
    )

    @model_validator(mode="after")
    def check_trigger_tag(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_trigger_tag(self.trigger, self.trigger_tag):
            raise ModelRetry(msg)
        return self

    @model_validator(mode="after")
    def check_tags_to_apply(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_tags_to_apply(self.action, self.tags_to_apply):
            raise ModelRetry(msg)
        return self

    @model_validator(mode="after")
    def check_self_only_actions(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_self_only_action(self.action, self.target):
            raise ModelRetry(msg)
        return self

    @model_validator(mode="after")
    def check_movement_target(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_movement_target(self.action, self.target):
            raise ModelRetry(msg)
        return self

    @model_validator(mode="after")
    def check_contact_body_trigger(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_contact_body_trigger(self.trigger, self.target):
            raise ModelRetry(msg)
        return self

    @model_validator(mode="after")
    def check_destroy_movement(self) -> Self:
        from pydantic_ai import ModelRetry

        if msg := _check_destroy_movement(self.trigger, self.action):
            raise ModelRetry(msg)
        return self


def compute_spec_cost(spec: BehaviorSpec) -> int:
    """Compute behavior cost from a BehaviorSpec (using power instead of intensity)."""
    base = BEHAVIOR_ACTION_COSTS[spec.action]
    modifier = 1 if spec.power == Power.HIGH else 0
    floor = SPAWN_EXPLODE_FLOOR if spec.action in _FLOORED_ACTIONS else 1
    return max(floor, base + modifier)


def expand_behavior_spec(spec: BehaviorSpec) -> Behavior:
    """Expand a simplified BehaviorSpec into a full Behavior with deterministic mappings.

    BehaviorSpec validators (ModelRetry) enforce action/target/trigger compatibility
    before this function is called. This function only maps power to granular parameters.
    The Behavior model validators (ValueError) serve as a safety net.
    """
    return Behavior(
        trigger=spec.trigger,
        action=spec.action,
        target=spec.target,
        intensity=_POWER_TO_INTENSITY[spec.power],
        range=_POWER_TO_RANGE[spec.power],
        speed=_POWER_TO_SPEED[spec.power],
        interval=_POWER_TO_INTERVAL[spec.power],
        tags_to_apply=spec.tags_to_apply,
        trigger_tag=spec.trigger_tag,
    )
