from enum import StrEnum


class Tag(StrEnum):
    # Physical State (5) — SOLID removed (implicit default), FLEXIBLE removed
    LIQUID = "LIQUID"
    GAS = "GAS"
    RIGID = "RIGID"
    HEAVY = "HEAVY"
    LIGHT = "LIGHT"
    # Temperature (3+1 internal) — HOT kept as internal-only (not in LLM vocab)
    FROZEN = "FROZEN"
    COLD = "COLD"
    HOT = "HOT"
    MOLTEN = "MOLTEN"
    BRITTLE = "BRITTLE"  # internal-only: added by freeze rules, shatterable by force
    # Energy (5)
    FLAMMABLE = "FLAMMABLE"
    HEAT_SOURCE = "HEAT_SOURCE"
    ELECTRIC = "ELECTRIC"
    MAGNETIC = "MAGNETIC"
    EXPLOSIVE = "EXPLOSIVE"
    # Surface (3) — SLIPPERY removed
    SHARP = "SHARP"
    STICKY = "STICKY"
    REFLECTIVE = "REFLECTIVE"
    # Mechanical (2)
    BOUNCY = "BOUNCY"
    BREAKABLE = "BREAKABLE"
    # Environmental (5+1 internal) — CORROSIVE renamed to ACIDIC
    FLOATING = "FLOATING"
    WIND_SOURCE = "WIND_SOURCE"
    ACIDIC = "ACIDIC"
    TOXIC = "TOXIC"
    WET = "WET"
    CORRODED = "CORRODED"  # internal-only: added by acid rules, vulnerable to force
    # Special (5) — GLOWING kept as internal-only, CONDUCTING renamed to METALLIC
    LIVING = "LIVING"
    GLOWING = "GLOWING"
    METALLIC = "METALLIC"
    INSULATING = "INSULATING"
    HOSTILE = "HOSTILE"


# Tags the LLM can pick. Internal-only tags are rule-applied at runtime.
LLM_VISIBLE_TAGS: frozenset[Tag] = frozenset(Tag) - {
    Tag.HOT,
    Tag.GLOWING,
    Tag.BRITTLE,
    Tag.CORRODED,
}

# One-line gameplay descriptions for hallucinated-tag retry messages.
TAG_DESCRIPTIONS: dict[Tag, str] = {
    Tag.LIQUID: "fluid physical state — flows, extinguishes fire, spreads WET",
    Tag.GAS: "gaseous — ultra-light, dispersed by wind, ionized by electricity",
    Tag.RIGID: "hard, unyielding — higher durability (200 HP)",
    Tag.HEAVY: "resists force, hard to push, immune to wind, crushes breakable things",
    Tag.LIGHT: "easily pushed, blown by WIND_SOURCE, player can push",
    Tag.FROZEN: "icy — slippery surface, shatters breakable things, melts from heat",
    Tag.COLD: "freezes LIQUID/WET on contact, solidifies MOLTEN, conducts through metal",
    Tag.MOLTEN: "extreme heat in liquid state (lava) — ignites, severely burns, destroys breakable",
    Tag.FLAMMABLE: "catches fire from HEAT_SOURCE/ELECTRIC — chain reaction fuel",
    Tag.HEAT_SOURCE: "produces fire — ignites flammable, melts ice, evaporates liquid",
    Tag.ELECTRIC: "shocks on contact, propagates through METALLIC/LIQUID, ignites flammable",
    Tag.MAGNETIC: "attracts METALLIC objects at range — continuous pull field",
    Tag.EXPLOSIVE: "detonates from heat or electricity — massive area damage",
    Tag.SHARP: "deals cut damage on contact to LIVING and BREAKABLE things",
    Tag.STICKY: "slows everything nearby to 25% speed — area denial trap",
    Tag.REFLECTIVE: "bounces back heat, electricity, and resists acid",
    Tag.BOUNCY: "high restitution — rebounds dramatically on impact",
    Tag.BREAKABLE: "fragile (50 HP) — vulnerable to sharp, acid, heavy, explosive, hostile",
    Tag.FLOATING: "defies gravity, hovers or rises — launched by wind, cancelled by heavy",
    Tag.WIND_SOURCE: "pushes LIGHT objects, disperses GAS, launches FLOATING — largest field range",
    Tag.ACIDIC: "dissolves materials — corrodes breakable/rigid/metallic, burns living",
    Tag.TOXIC: "poisons LIVING things, cascades toxic cloud through GAS — medium range field",
    Tag.WET: "damp/soaked — amplifies electric shock, freezes easier, resists fire",
    Tag.LIVING: "a creature or organism — targetable by NEAREST_LIVING, vulnerable to many hazards",
    Tag.METALLIC: "conducts electricity and heat, attracted by magnets, dissolved by acid",
    Tag.INSULATING: "blocks electricity and heat propagation — powerful defensive modifier",
    Tag.HOSTILE: "aggressive danger aura — damage + knockback at close range, hostile clash",
}

# Auto-correction: if LLM outputs HOT, silently replace with HEAT_SOURCE.
TAG_AUTO_CORRECTIONS: dict[str, Tag] = {
    "HOT": Tag.HEAT_SOURCE,
    "SOLID": Tag.RIGID,  # closest equivalent for objects that "should be solid"
    "CORROSIVE": Tag.ACIDIC,
    "CONDUCTING": Tag.METALLIC,
    "SLIPPERY": Tag.FROZEN,
    "FLEXIBLE": Tag.BOUNCY,
    "GLOWING": Tag.HEAT_SOURCE,  # closest gameplay equivalent
    "BRITTLE": Tag.FROZEN,  # closest LLM-visible equivalent
    "CORRODED": Tag.ACIDIC,  # closest LLM-visible equivalent
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
    frozenset({Tag.LIQUID, Tag.GAS}),
    frozenset({Tag.METALLIC, Tag.INSULATING}),
    frozenset({Tag.WET, Tag.MOLTEN}),
    frozenset({Tag.WET, Tag.HEAT_SOURCE}),
    frozenset({Tag.BRITTLE, Tag.LIQUID}),
    frozenset({Tag.BRITTLE, Tag.GAS}),
]
