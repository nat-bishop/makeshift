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


class EquipmentSlot(BaseModel):
    slot_name: str  # "hand" | "back" | "head"
    object_id: str | None = None


class Session(BaseModel):
    id: str
    created_at: str
    budget_used: float = 0.0
    level_progress: int = 0
    objects: list[WorldObject] = Field(default_factory=list)
    inventory: list[InventorySlot] = Field(default_factory=list)
    equipment: list[EquipmentSlot] = Field(default_factory=list)
