from pydantic import BaseModel

from app.models.effects import Effect
from app.models.tags import Tag


class InteractionRule(BaseModel):
    rule_id: str
    name: str
    tags_required_a: set[Tag]
    tags_required_b: set[Tag]  # empty set = wildcard (matches any)
    priority: int
    bidirectional: bool
    cascade_eligible: bool
    effects: list[Effect]
