from enum import StrEnum

from pydantic import BaseModel

from app.models.effects import Effect
from app.models.tags import Tag


class TriggerMode(StrEnum):
    CONTACT = "CONTACT"
    FIELD = "FIELD"


class InteractionRule(BaseModel):
    rule_id: str
    name: str
    tags_required_a: set[Tag]
    tags_required_b: set[Tag]  # empty set = wildcard (matches any)
    priority: int
    bidirectional: bool
    cascade_eligible: bool
    effects: list[Effect]
    tags_blocked_by: set[Tag] = set()  # rule skipped if B-side object has any of these
    trigger_mode: TriggerMode = TriggerMode.CONTACT
