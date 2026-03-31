import re
from enum import StrEnum
from typing import Self, TypeVar

from pydantic import BaseModel, model_validator

from app.models.tags import Tag


class BehaviorParseError(ValueError):
    """Raised when a behavior notation string cannot be parsed."""


class BehaviorTrigger(StrEnum):
    # LLM-visible triggers
    ALWAYS = "ALWAYS"
    ON_TIMER = "ON_TIMER"
    ON_PROXIMITY = "ON_PROXIMITY"
    ON_CONTACT = "ON_CONTACT"
    ON_DAMAGED = "ON_DAMAGED"
    ON_HEALTH_LOW = "ON_HEALTH_LOW"
    ON_TAG_ADDED = "ON_TAG_ADDED"
    # Engine-internal (not in LLM vocab, used by tag-implied behaviors)
    ON_CREATE = "ON_CREATE"
    ON_DESTROY = "ON_DESTROY"


LLM_VISIBLE_TRIGGERS: frozenset[BehaviorTrigger] = frozenset(BehaviorTrigger) - {
    BehaviorTrigger.ON_CREATE,
    BehaviorTrigger.ON_DESTROY,
}


class BehaviorAction(StrEnum):
    # LLM-visible actions
    MOVE_TOWARD = "MOVE_TOWARD"
    MOVE_AWAY = "MOVE_AWAY"
    SPAWN_PROJECTILE = "SPAWN_PROJECTILE"
    EXPLODE = "EXPLODE"
    HEAL = "HEAL"
    ADD_TAGS = "ADD_TAGS"
    SELF_DESTRUCT = "SELF_DESTRUCT"
    # Engine-internal (not in LLM vocab, used by tag-implied behaviors)
    PATROL = "PATROL"
    APPLY_FORCE = "APPLY_FORCE"
    ATTRACT = "ATTRACT"
    REMOVE_TAGS = "REMOVE_TAGS"


LLM_VISIBLE_ACTIONS: frozenset[BehaviorAction] = frozenset(BehaviorAction) - {
    BehaviorAction.PATROL,
    BehaviorAction.APPLY_FORCE,
    BehaviorAction.ATTRACT,
    BehaviorAction.REMOVE_TAGS,
}


class BehaviorTarget(StrEnum):
    SELF = "SELF"
    NEAREST_LIVING = "NEAREST_LIVING"
    NEAREST_PLAYER = "NEAREST_PLAYER"
    # Internal-only: auto-inferred from contact triggers, not in LLM vocab
    CONTACT_BODY = "CONTACT_BODY"


LLM_VISIBLE_TARGETS: frozenset[BehaviorTarget] = frozenset(BehaviorTarget) - {
    BehaviorTarget.CONTACT_BODY
}


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


# Actions that always target SELF (client ignores the target field)
_SELF_ONLY_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.SELF_DESTRUCT, BehaviorAction.EXPLODE, BehaviorAction.PATROL}
)

# Movement actions that need a real target (target=SELF produces a zero vector)
_DIRECTIONAL_MOVEMENT_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY}
)

# All movement actions (including engine-internal PATROL)
_ALL_MOVEMENT_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY, BehaviorAction.PATROL}
)

# Auto-correct common hallucinated targets (avoids wasting a retry)
_TARGET_AUTO_CORRECTIONS: dict[str, BehaviorTarget] = {
    "NEAREST_OBJECT": BehaviorTarget.NEAREST_LIVING,
    "NEAREST_ENEMY": BehaviorTarget.NEAREST_LIVING,
    "NEAREST_CREATURE": BehaviorTarget.NEAREST_LIVING,
}

# Triggers that support CONTACT_BODY target
_CONTACT_BODY_TRIGGERS: frozenset[BehaviorTrigger] = frozenset(
    {
        BehaviorTrigger.ON_CONTACT,
        BehaviorTrigger.ON_DAMAGED,
        BehaviorTrigger.ON_PROXIMITY,
    }
)


# ---------------------------------------------------------------------------
# Target auto-inference — infer target from trigger + action when omitted
# ---------------------------------------------------------------------------

_TRIGGER_DEFAULT_TARGETS: dict[BehaviorTrigger, BehaviorTarget] = {
    BehaviorTrigger.ON_CONTACT: BehaviorTarget.CONTACT_BODY,
    BehaviorTrigger.ON_DAMAGED: BehaviorTarget.CONTACT_BODY,
    BehaviorTrigger.ON_PROXIMITY: BehaviorTarget.NEAREST_LIVING,
    BehaviorTrigger.ALWAYS: BehaviorTarget.NEAREST_LIVING,
    BehaviorTrigger.ON_TIMER: BehaviorTarget.SELF,
    BehaviorTrigger.ON_HEALTH_LOW: BehaviorTarget.SELF,
    BehaviorTrigger.ON_TAG_ADDED: BehaviorTarget.SELF,
    BehaviorTrigger.ON_CREATE: BehaviorTarget.SELF,
    BehaviorTrigger.ON_DESTROY: BehaviorTarget.SELF,
}


def infer_target(
    trigger: BehaviorTrigger, action: BehaviorAction
) -> BehaviorTarget:
    """Infer the best target when the LLM omits one."""
    if action in _SELF_ONLY_ACTIONS:
        return BehaviorTarget.SELF
    default = _TRIGGER_DEFAULT_TARGETS.get(trigger, BehaviorTarget.NEAREST_LIVING)
    if action in _DIRECTIONAL_MOVEMENT_ACTIONS and default == BehaviorTarget.SELF:
        return BehaviorTarget.NEAREST_LIVING
    return default


# ---------------------------------------------------------------------------
# Shared validation helpers — used by both Behavior and BehaviorSpec.
# Return an error message string if invalid, None if OK.
# ---------------------------------------------------------------------------


def _check_trigger_tag(
    trigger: BehaviorTrigger, trigger_tag: Tag | None
) -> str | None:
    if trigger == BehaviorTrigger.ON_TAG_ADDED:
        if trigger_tag is None:
            return "ON_TAG_ADDED trigger requires trigger_tag to specify which tag to watch."
    elif trigger_tag is not None:
        return f"trigger_tag is only valid with ON_TAG_ADDED trigger, not {trigger}."
    return None


def _check_tags_to_apply(
    action: BehaviorAction, tags_to_apply: list[Tag] | None
) -> str | None:
    if action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS} and not tags_to_apply:
        return f"{action} action requires tags_to_apply to specify which tags."
    return None


def _check_self_only_action(
    action: BehaviorAction, target: BehaviorTarget
) -> str | None:
    if action in _SELF_ONLY_ACTIONS and target != BehaviorTarget.SELF:
        return f"{action} always affects this object. target must be SELF."
    return None


def _check_movement_target(
    action: BehaviorAction, target: BehaviorTarget
) -> str | None:
    if action in _DIRECTIONAL_MOVEMENT_ACTIONS and target == BehaviorTarget.SELF:
        return (
            f"{action} needs a target to move toward/away from. "
            f"SELF is not valid. "
            f"Use NEAREST_LIVING or NEAREST_PLAYER."
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


def _check_destroy_movement(
    trigger: BehaviorTrigger, action: BehaviorAction
) -> str | None:
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
    """Internal intermediate model. Produced by parse_behavior_string(), consumed by
    expand_behavior_spec(). Not directly used as LLM output — the LLM outputs string
    notation which is parsed into this model.
    """

    trigger: BehaviorTrigger
    action: BehaviorAction
    target: BehaviorTarget = BehaviorTarget.NEAREST_LIVING
    power: Power = Power.MEDIUM
    trigger_tag: Tag | None = None
    tags_to_apply: list[Tag] | None = None

    @model_validator(mode="after")
    def check_trigger_tag(self) -> Self:
        if msg := _check_trigger_tag(self.trigger, self.trigger_tag):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_tags_to_apply(self) -> Self:
        if msg := _check_tags_to_apply(self.action, self.tags_to_apply):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_self_only_actions(self) -> Self:
        if msg := _check_self_only_action(self.action, self.target):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_movement_target(self) -> Self:
        if msg := _check_movement_target(self.action, self.target):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_contact_body_trigger(self) -> Self:
        if msg := _check_contact_body_trigger(self.trigger, self.target):
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_destroy_movement(self) -> Self:
        if msg := _check_destroy_movement(self.trigger, self.action):
            raise ValueError(msg)
        return self


def expand_behavior_spec(spec: BehaviorSpec) -> Behavior:
    """Expand a simplified BehaviorSpec into a full Behavior with deterministic mappings."""
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


# ---------------------------------------------------------------------------
# Behavior string notation parser
# ---------------------------------------------------------------------------

_PARAMETRIC_RE = re.compile(r"^(\w+)\(([^)]+)\)$")


_E = TypeVar("_E", bound=StrEnum)


def _parse_enum(value: str, enum_cls: type[_E], label: str) -> _E:
    """Look up a StrEnum member by value (case-insensitive)."""
    stripped = value.strip()
    for candidate in (stripped, stripped.upper(), stripped.lower()):
        try:
            return enum_cls(candidate)
        except ValueError:
            continue
    valid = ", ".join(m.value for m in enum_cls)
    raise BehaviorParseError(f"Unknown {label} '{value}'. Valid: {valid}")


def _parse_tag(value: str) -> Tag:
    """Look up a Tag by name (case-insensitive)."""
    return _parse_enum(value, Tag, "tag")


def _parse_parametric(token: str) -> tuple[str, list[str]]:
    """Parse 'NAME(arg1, arg2)' or plain 'NAME'. Returns (name, args)."""
    m = _PARAMETRIC_RE.match(token)
    if m:
        name = m.group(1)
        args = [a.strip() for a in m.group(2).split(",") if a.strip()]
        if not args:
            raise BehaviorParseError(
                f"Empty parentheses in '{token}'. Provide arguments or remove the parens."
            )
        return name, args
    if "(" in token or ")" in token:
        raise BehaviorParseError(f"Malformed parentheses in '{token}'.")
    return token.strip(), []


def parse_behavior_string(s: str) -> BehaviorSpec:
    """Parse behavior notation into a BehaviorSpec.

    Format: TRIGGER -> ACTION -> TARGET, power=POWER
    Parametric: ON_TAG_ADDED(TAG), ADD_TAGS(TAG1, TAG2), REMOVE_TAGS(TAG1, TAG2)

    Target is optional — auto-inferred from trigger when omitted.

    Raises BehaviorParseError for format issues. BehaviorSpec validators raise
    ValueError for semantic issues (e.g. EXPLODE with non-SELF target).
    """
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if not s:
        raise BehaviorParseError("Empty behavior string.")

    s = s.replace("->", "\u2192")
    parts = [p.strip() for p in s.split("\u2192")]

    if len(parts) < 2:
        raise BehaviorParseError(
            f"Expected TRIGGER -> ACTION -> TARGET, got '{s}'."
        )
    if len(parts) > 3:
        raise BehaviorParseError(
            f"Too many parts (expected 2-3 separated by ->), got {len(parts)}."
        )

    # --- Trigger ---
    trigger_raw, trigger_args = _parse_parametric(parts[0])
    trigger = _parse_enum(trigger_raw, BehaviorTrigger, "trigger")
    trigger_tag = _parse_tag(trigger_args[0]) if trigger_args else None

    # --- Action (strip trailing kwargs like ", power=high" in 2-part form) ---
    power = Power.MEDIUM
    action_segment = parts[1]
    if len(parts) == 2 and "," in action_segment and "(" not in action_segment:
        # e.g., "EXPLODE, power=high" — split out kwargs before parsing action
        segments = [seg.strip() for seg in action_segment.split(",")]
        action_segment = segments[0]
        for seg in segments[1:]:
            if "=" in seg:
                key, val = seg.split("=", 1)
                if key.strip().lower() == "power":
                    power = _parse_enum(val.strip(), Power, "power")

    action_raw, action_args = _parse_parametric(action_segment)
    action = _parse_enum(action_raw, BehaviorAction, "action")
    tags_to_apply = [_parse_tag(a) for a in action_args] if action_args else None

    # --- Target + kwargs ---
    if len(parts) == 3:
        segments = [seg.strip() for seg in parts[2].split(",")]
        target_str = segments[0]
        # Auto-correct common hallucinated targets
        target_upper = target_str.strip().upper()
        if target_upper in _TARGET_AUTO_CORRECTIONS:
            target = _TARGET_AUTO_CORRECTIONS[target_upper]
        else:
            target = _parse_enum(target_str, BehaviorTarget, "target")
        for seg in segments[1:]:
            if "=" not in seg:
                continue
            key, val = seg.split("=", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "power":
                power = _parse_enum(val, Power, "power")
    else:
        target = infer_target(trigger, action)

    return BehaviorSpec(
        trigger=trigger,
        action=action,
        target=target,
        power=power,
        trigger_tag=trigger_tag,
        tags_to_apply=tags_to_apply,
    )
