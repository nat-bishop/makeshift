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
    Tag.LIQUID: "fluid that flows and pools. Water, oil, slime",
    Tag.GAS: "airborne, dispersed substance. Smoke, steam, poison clouds",
    Tag.RIGID: "hard, unyielding material (200 HP). Stone, metal, bone, hardwood",
    Tag.HEAVY: "dense and massive. Anvils, boulders, safes. Immovable by wind or pushing",
    Tag.LIGHT: "very low mass. Feathers, paper, balloons. Blown by WIND_SOURCE, pushed by players",
    Tag.FROZEN: "encased in or made of ice. Ice blocks, frost crystals. Brittle and slippery",
    Tag.COLD: "actively radiates cold. Freezers, ice elementals, snow clouds",
    Tag.MOLTEN: "superheated liquid. Lava, molten metal, magma",
    Tag.FLAMMABLE: "combustible. Wood, cloth, paper, oil. Ignited by HEAT_SOURCE or ELECTRIC",
    Tag.HEAT_SOURCE: "actively produces heat or fire. Torches, campfires, fire elementals",
    Tag.ELECTRIC: "electrical charge. Lightning, live wires. Propagates through METALLIC/LIQUID",
    Tag.MAGNETIC: "magnetic field. Magnets, lodestones. Pulls METALLIC objects at range",
    Tag.EXPLOSIVE: "volatile, detonates under stress. Dynamite, grenades, gas canisters",
    Tag.SHARP: "has a cutting edge or point. Swords, thorns, broken glass, claws",
    Tag.STICKY: "adhesive surface. Honey, tar, spider webs, glue. Slows nearby to 25% speed",
    Tag.REFLECTIVE: "smooth, mirror-like surface. Shields, mirrors, polished metal",
    Tag.BOUNCY: "elastic, high restitution. Rubber balls, springs, trampolines",
    Tag.BREAKABLE: "fragile, easily destroyed (50 HP). Glass, pottery, eggshells",
    Tag.FLOATING: "buoyant, defies gravity. Balloons, ghosts, clouds, bubbles",
    Tag.WIND_SOURCE: "strong air currents. Fans, tornados. Pushes LIGHT, disperses GAS",
    Tag.ACIDIC: "corrosive chemical. Acid pools, chemical waste, digestive fluid",
    Tag.TOXIC: "poisonous substance. Venom, toxic mushrooms, noxious fumes. Cascades through GAS",
    Tag.WET: "damp or soaked. Amplifies ELECTRIC shock, freezes from COLD, resists fire",
    Tag.LIVING: "biological creature or organism. Animals, monsters, insects",
    Tag.METALLIC: "made of metal. Swords, armor, coins, chains. Conducts heat and electricity",
    Tag.INSULATING: "blocks energy transfer. Rubber coating, ceramic, thick glass",
    Tag.HOSTILE: "aggressive, damage + knockback nearby. Two HOSTILE objects fight each other",
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
    frozenset({Tag.FROZEN, Tag.HEAT_SOURCE}),
    frozenset({Tag.FROZEN, Tag.HOT}),
    frozenset({Tag.COLD, Tag.HEAT_SOURCE}),
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
