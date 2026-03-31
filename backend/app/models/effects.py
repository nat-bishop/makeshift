from enum import StrEnum

from pydantic import BaseModel

from app.models.tags import Tag


class EffectType(StrEnum):
    DAMAGE = "DAMAGE"
    HEAL = "HEAL"
    ADD_TAG = "ADD_TAG"
    REMOVE_TAG = "REMOVE_TAG"
    APPLY_FORCE = "APPLY_FORCE"
    APPLY_SLOW = "APPLY_SLOW"


class EffectTarget(StrEnum):
    A = "a"
    B = "b"
    BOTH = "both"


class Effect(BaseModel):
    effect_type: EffectType
    target: EffectTarget
    message: str = ""
    # DAMAGE / HEAL parameters (effect_type distinguishes intent)
    damage_amount: float | None = None
    tick_interval: float | None = None  # If > 0, DAMAGE becomes DOT
    tick_duration: float | None = None
    # ADD_TAG / REMOVE_TAG parameters
    tag: Tag | None = None
    tag_duration: float | None = None  # only with ADD_TAG; 0.0 = permanent
    # APPLY_FORCE parameters
    force_magnitude: float | None = None
    # APPLY_SLOW parameters
    slow_factor: float | None = None  # 0.25 = 25% speed; continuous per-frame field effect
