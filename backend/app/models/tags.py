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
    WET = "WET"
    # Special (5)
    LIVING = "LIVING"
    GLOWING = "GLOWING"
    CONDUCTING = "CONDUCTING"
    INSULATING = "INSULATING"
    HOSTILE = "HOSTILE"


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
    frozenset({Tag.HEAT_SOURCE, Tag.FLAMMABLE}),
    frozenset({Tag.WET, Tag.MOLTEN}),
    frozenset({Tag.WET, Tag.HEAT_SOURCE}),
]

