"""V3 game object blueprint — LLM-generated physics, affordance, autonomous flag."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PhysicsProperties(BaseModel):
    """All physics values set at creation time by parallel 1-token LLM calls."""

    mass_kg: float = Field(ge=0.001, le=100000)
    height_cm: int = Field(ge=1, le=5000)
    friction: int = Field(ge=0, le=100)
    bounce: int = Field(ge=0, le=100)
    gravity: int = Field(ge=0, le=100)

    @property
    def damping(self) -> float:
        """Derived: light large things (feather) have high damping,
        heavy small things (bullet) have low damping."""
        return self.height_cm / (self.mass_kg * 100.0 + 10.0)

    @property
    def size_category(self) -> str:
        if self.height_cm < 10:
            return "tiny"
        if self.height_cm < 50:
            return "small"
        if self.height_cm < 150:
            return "medium"
        if self.height_cm < 400:
            return "large"
        return "huge"


class Destructibility(BaseModel):
    armor: int = Field(ge=0, le=100, default=30)
    hp: int = Field(ge=0, le=100, default=50)
    indestructible: bool = False


class GameObjectBlueprint(BaseModel):
    """Complete V3 object definition. Serialized as JSON in the objects DB table."""

    id: str
    name: str
    description: str  # original player input
    visual_description: str
    physics: PhysicsProperties
    destructibility: Destructibility
    affordance: int = Field(ge=0, le=3, default=3)  # 0=carry 1=mount 2=climb 3=nothing
    autonomous: bool = False
    has_field: bool = False
    field_range_cm: int = Field(default=0, ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def check_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Name cannot be empty")
        if len(name.split()) > 3:
            raise ValueError(f'Name "{name}" exceeds 3 words')
        return name
