from typing import Literal

from pydantic import BaseModel, Field


class VisualDescriptor(BaseModel):
    visual_description: str = Field(description="1-2 sentences for sprite gen")
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = "medium"


class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str  # original player input

    # Physics (LLM-generated, cached by name)
    mass_kg: float = Field(ge=0.001, le=100000)
    height_cm: int = Field(ge=1, le=5000)
    friction: int = Field(ge=0, le=100)
    bounce: int = Field(ge=0, le=100)
    gravity: int = Field(ge=0, le=100)

    # Destructibility
    armor: int = Field(ge=0, le=100)
    hp: int = Field(ge=0, le=100)
    indestructible: bool = False

    # Field
    has_field: bool = False
    field_range_cm: int = Field(default=0, ge=0, le=5000)

    # Classification
    autonomous: bool = False
    affordance: int = Field(default=3, ge=0, le=3)  # 0=carry, 1=mount, 2=climb, 3=nothing

    # Visual
    visual_descriptor: VisualDescriptor

    # Destruction
    destruction_result_name: str = ""  # e.g. "pile of charred splinters"

    # Runtime (starts empty, modified by interactions)
    states: list[str] = Field(default_factory=list)
