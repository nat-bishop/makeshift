from enum import StrEnum

from pydantic import BaseModel

from app.models.tags import Tag


class EffectType(StrEnum):
    DAMAGE = "DAMAGE"
    DESTROY = "DESTROY"
    IGNITE = "IGNITE"
    EXTINGUISH = "EXTINGUISH"
    FREEZE = "FREEZE"
    MELT = "MELT"
    TRANSFORM = "TRANSFORM"
    APPLY_FORCE = "APPLY_FORCE"
    CORRODE = "CORRODE"
    ELECTRIFY = "ELECTRIFY"
    ADD_TAG = "ADD_TAG"
    REMOVE_TAG = "REMOVE_TAG"


class EffectTarget(StrEnum):
    A = "a"
    B = "b"
    BOTH = "both"


class Effect(BaseModel):
    effect_type: EffectType
    target: EffectTarget
    damage_amount: float | None = None
    tags_to_add: list[Tag] | None = None
    tags_to_remove: list[Tag] | None = None
    force_magnitude: float | None = None
    message: str
