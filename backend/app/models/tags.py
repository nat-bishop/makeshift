from enum import StrEnum


class Tag(StrEnum):
    # Physical State (7)
    SOLID = "SOLID"
    LIQUID = "LIQUID"
    GAS = "GAS"
    RIGID = "RIGID"
    FLEXIBLE = "FLEXIBLE"
    HEAVY = "HEAVY"
    LIGHT = "LIGHT"
    # Temperature (4)
    FROZEN = "FROZEN"
    COLD = "COLD"
    HOT = "HOT"
    MOLTEN = "MOLTEN"
    # Energy (5)
    FLAMMABLE = "FLAMMABLE"
    HEAT_SOURCE = "HEAT_SOURCE"
    ELECTRIC = "ELECTRIC"
    MAGNETIC = "MAGNETIC"
    EXPLOSIVE = "EXPLOSIVE"
    # Surface (4)
    SHARP = "SHARP"
    STICKY = "STICKY"
    SLIPPERY = "SLIPPERY"
    REFLECTIVE = "REFLECTIVE"
    # Mechanical (2)
    BOUNCY = "BOUNCY"
    BREAKABLE = "BREAKABLE"
    # Environmental (4)
    FLOATING = "FLOATING"
    WIND_SOURCE = "WIND_SOURCE"
    CORROSIVE = "CORROSIVE"
    TOXIC = "TOXIC"
    # Special (4)
    LIVING = "LIVING"
    GLOWING = "GLOWING"
    CONDUCTING = "CONDUCTING"
    INSULATING = "INSULATING"


TAG_POWER_COSTS: dict[Tag, int] = {
    # Cost 1
    Tag.SOLID: 1,
    Tag.LIQUID: 1,
    Tag.GAS: 1,
    Tag.RIGID: 1,
    Tag.FLEXIBLE: 1,
    Tag.LIGHT: 1,
    Tag.COLD: 1,
    Tag.FLAMMABLE: 1,
    Tag.SLIPPERY: 1,
    Tag.BREAKABLE: 1,
    # Cost 2
    Tag.HEAVY: 2,
    Tag.FROZEN: 2,
    Tag.HOT: 2,
    Tag.SHARP: 2,
    Tag.STICKY: 2,
    Tag.REFLECTIVE: 2,
    Tag.BOUNCY: 2,
    Tag.FLOATING: 2,
    Tag.GLOWING: 2,
    Tag.CONDUCTING: 2,
    Tag.INSULATING: 2,
    # Cost 3
    Tag.HEAT_SOURCE: 3,
    Tag.MAGNETIC: 3,
    Tag.WIND_SOURCE: 3,
    Tag.LIVING: 3,
    # Cost 4
    Tag.ELECTRIC: 4,
    Tag.CORROSIVE: 4,
    Tag.TOXIC: 4,
    Tag.MOLTEN: 4,
    # Cost 5
    Tag.EXPLOSIVE: 5,
}

TAG_CONTRADICTIONS: list[frozenset[Tag]] = [
    frozenset({Tag.FROZEN, Tag.MOLTEN}),
    frozenset({Tag.FROZEN, Tag.HOT}),
    frozenset({Tag.COLD, Tag.HOT}),
    frozenset({Tag.COLD, Tag.MOLTEN}),
    frozenset({Tag.HEAVY, Tag.LIGHT}),
    frozenset({Tag.LIQUID, Tag.RIGID}),
    frozenset({Tag.GAS, Tag.RIGID}),
    frozenset({Tag.GAS, Tag.HEAVY}),
    frozenset({Tag.SOLID, Tag.LIQUID}),
    frozenset({Tag.SOLID, Tag.GAS}),
    frozenset({Tag.LIQUID, Tag.GAS}),
    frozenset({Tag.STICKY, Tag.SLIPPERY}),
    frozenset({Tag.CONDUCTING, Tag.INSULATING}),
    frozenset({Tag.REFLECTIVE, Tag.STICKY}),
]

OBJECT_TAG_BUDGET: int = 10

SIZE_PIXEL_MAP: dict[str, int] = {
    "tiny": 32,
    "small": 48,
    "medium": 64,
    "large": 96,
    "huge": 128,
}
