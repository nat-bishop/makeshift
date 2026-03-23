from pydantic import BaseModel, Field

from app.models.blueprint import GameObjectBlueprint


class WorldObject(BaseModel):
    object_id: str
    blueprint: GameObjectBlueprint
    x: float = 0.0
    y: float = 0.0
    durability: float = 0.0


class Session(BaseModel):
    id: str
    created_at: str
    budget_used: float = 0.0
    budget_limit: float = 1.0
    objects: list[WorldObject] = Field(default_factory=list)

    @property
    def budget_remaining(self) -> float:
        return self.budget_limit - self.budget_used
