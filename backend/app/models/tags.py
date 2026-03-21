from __future__ import annotations

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
    # Mechanical (3)
    BOUNCY = "BOUNCY"
    CLIMBABLE = "CLIMBABLE"
    BREAKABLE = "BREAKABLE"
    # Interaction (2)
    WEARABLE = "WEARABLE"
    TOOL = "TOOL"
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
    Tag.CLIMBABLE: 2,
    Tag.WEARABLE: 2,
    Tag.TOOL: 2,
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
]

OBJECT_TAG_BUDGET: int = 10

EQUIP_SLOT_MAP: dict[str, str] = {
    "sword": "hand",
    "axe": "hand",
    "hammer": "hand",
    "wand": "hand",
    "tool": "hand",
    "wrench": "hand",
    "torch": "hand",
    "fan": "hand",
    "shield": "back",
    "jetpack": "back",
    "cape": "back",
    "wings": "back",
    "helmet": "head",
    "crown": "head",
    "goggles": "head",
}

TRANSFERABLE_TAGS: set[Tag] = {
    Tag.HEAT_SOURCE,
    Tag.COLD,
    Tag.SHARP,
    Tag.ELECTRIC,
    Tag.MAGNETIC,
    Tag.WIND_SOURCE,
    Tag.CORROSIVE,
    Tag.TOXIC,
    Tag.FLOATING,
    Tag.GLOWING,
    Tag.REFLECTIVE,
    Tag.INSULATING,
    Tag.CONDUCTING,
    Tag.STICKY,
}
