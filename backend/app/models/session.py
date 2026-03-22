from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.blueprint import GameObjectBlueprint


class WorldObject(BaseModel):
    object_id: str
    blueprint: GameObjectBlueprint
    x: float = 0.0
    y: float = 0.0
    durability: float = 0.0


class InventorySlot(BaseModel):
    slot: int
    object_id: str | None = None


class EquipmentSlots(BaseModel):
    hand: str | None = None
    back: str | None = None
    head: str | None = None


class Session(BaseModel):
    id: str
    created_at: str
    budget_used: float = 0.0
    budget_limit: float = 1.0
    current_level: int = 1
    levels_completed: list[int] = Field(default_factory=list)
    objects: list[WorldObject] = Field(default_factory=list)
    inventory: list[InventorySlot] = Field(default_factory=list)
    equipment: EquipmentSlots = Field(default_factory=EquipmentSlots)

    @property
    def budget_remaining(self) -> float:
        return self.budget_limit - self.budget_used
