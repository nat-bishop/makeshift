"""V3 game object blueprint — LLM-generated physics, affordance, autonomous flag."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Durability tier → HP mapping. No armor/damage-reduction mechanic.
DURABILITY_HP: dict[int, int] = {
    0: 5,  # fragile (paper, balloon)
    1: 15,  # weak (glass, web)
    2: 40,  # normal (wood, flesh)
    3: 80,  # tough (stone, bone)
    4: 150,  # hardy (steel, diamond)
    5: 300,  # fortified (castle wall)
    # 6 = indestructible (999999 HP)
}

DURABILITY_NAMES: dict[int, str] = {
    0: "fragile",
    1: "weak",
    2: "normal",
    3: "tough",
    4: "hardy",
    5: "fortified",
    6: "indestructible",
}

# Speed tier → name mapping (autonomous creatures only).
SPEED_NAMES: dict[int, str] = {
    0: "sluggish",
    1: "slow",
    2: "normal",
    3: "fast",
    4: "rapid",
}

# Speed tier → movement multiplier applied to base speeds in creature_behavior.gd.
SPEED_MULTIPLIER: dict[int, float] = {
    0: 0.3,
    1: 0.6,
    2: 1.0,
    3: 1.5,
    4: 2.0,
}

# Surface type → friction coefficient mapping.
SURFACE_FRICTION: dict[int, float] = {
    0: 0.05,  # slippery (ice, oil)
    1: 0.5,  # normal (wood, metal, stone)
    2: 1.0,  # sticky (glue, tar, tape)
}


def durability_to_hp(durability: int) -> int:
    """Map durability tier (0-6) to starting HP."""
    if durability >= 6:
        return 999999
    return DURABILITY_HP.get(durability, 40)


class PhysicsProperties(BaseModel):
    """All physics values set at creation time by parallel 1-token LLM calls."""

    mass_kg: float = Field(ge=0.001, le=100000)
    height_cm: int = Field(ge=1, le=5000)
    surface: int = Field(ge=0, le=2, default=1)  # 0=slippery 1=normal 2=sticky
    bounce: int = Field(ge=0, le=100)
    gravity: int = Field(ge=0, le=100)

    @property
    def damping(self) -> float:
        """Derived: light large things (feather) have high damping,
        heavy small things (bullet) have low damping."""
        return self.height_cm / (self.mass_kg * 100.0 + 10.0)

    @property
    def friction(self) -> float:
        """Friction coefficient derived from surface type."""
        return SURFACE_FRICTION.get(self.surface, 0.5)

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


class GameObjectBlueprint(BaseModel):
    """Complete V3 object definition. Serialized as JSON in the objects DB table."""

    id: str
    name: str
    description: str  # original player input
    visual_description: str
    physics: PhysicsProperties
    durability: int = Field(ge=0, le=6, default=2)  # 0=fragile .. 6=indestructible
    affordance: int = Field(ge=0, le=3, default=3)  # 0=carry 1=mount 2=climb 3=nothing
    autonomous: bool = False
    speed: int = Field(ge=0, le=4, default=2)  # 0=sluggish .. 4=rapid (autonomous only)
    initial_states: list[int] = Field(default_factory=list)  # state IDs this object spawns with
    susceptible_states: list[int] = Field(default_factory=list)  # state IDs that can spread to this
    destruction_result_name: str = ""

    @field_validator("name")
    @classmethod
    def check_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Name cannot be empty")
        if len(name.split()) > 5:
            raise ValueError(f'Name "{name}" exceeds 5 words')
        return name

    @property
    def starting_hp(self) -> int:
        """HP derived from durability tier."""
        return durability_to_hp(self.durability)

    @property
    def is_indestructible(self) -> bool:
        return self.durability >= 6
