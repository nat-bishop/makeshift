from enum import StrEnum


class Category(StrEnum):
    CREATURE = "CREATURE"
    FOOD = "FOOD"
    WEAPON = "WEAPON"
    PLANT = "PLANT"
    VALUABLE = "VALUABLE"
    VEHICLE = "VEHICLE"
    TOOL = "TOOL"


CATEGORY_DESCRIPTIONS: dict[Category, str] = {
    Category.CREATURE: "A living or animated being — animals, monsters, people, insects.",
    Category.FOOD: "Something edible or consumable — fruit, meat, potions, snacks.",
    Category.WEAPON: "Made to deal damage — swords, bombs, bows, traps.",
    Category.PLANT: "A plant or fungus — trees, flowers, vines, mushrooms.",
    Category.VALUABLE: "Precious or worth collecting — treasure, coins, gems, rare items.",
    Category.VEHICLE: "Something rideable or that carries things — carts, boats, horses.",
    Category.TOOL: "A utility object — buckets, ropes, levers, keys, shields.",
}

# Valid values for BehaviorVerbSpec.target_tag — categories + select state tags.
BEHAVIOR_TARGETS: frozenset[str] = frozenset(
    {c.value for c in Category} | {"HOSTILE", "HEAT_SOURCE"}
)


class Tag(StrEnum):
    # Physical State
    LIQUID = "LIQUID"
    GAS = "GAS"
    RIGID = "RIGID"
    HEAVY = "HEAVY"
    LIGHT = "LIGHT"
    # Temperature
    FROZEN = "FROZEN"
    COLD = "COLD"
    HOT = "HOT"  # internal-only: derived from substance/element
    MOLTEN = "MOLTEN"
    BRITTLE = "BRITTLE"  # internal-only: added by freeze rules
    # Energy
    FLAMMABLE = "FLAMMABLE"
    HEAT_SOURCE = "HEAT_SOURCE"
    ELECTRIC = "ELECTRIC"
    MAGNETIC = "MAGNETIC"
    EXPLOSIVE = "EXPLOSIVE"
    # Surface
    SHARP = "SHARP"
    STICKY = "STICKY"
    REFLECTIVE = "REFLECTIVE"
    # Mechanical
    BOUNCY = "BOUNCY"
    BREAKABLE = "BREAKABLE"
    # Environmental
    FLYING = "FLYING"
    WIND_SOURCE = "WIND_SOURCE"
    ACIDIC = "ACIDIC"
    TOXIC = "TOXIC"
    WET = "WET"
    CORRODED = "CORRODED"  # internal-only: added by acid rules
    # Special
    LIVING = "LIVING"
    GLOWING = "GLOWING"  # internal-only: smolder ignition + creature attraction
    METALLIC = "METALLIC"
    INSULATING = "INSULATING"
    HOSTILE = "HOSTILE"


# LLM picks 0-3 tags from this set. Substance/element absorb the rest.
# LIVING auto-derived from CREATURE category. HOSTILE auto-derived from destroy verb.
LLM_VISIBLE_TAGS: frozenset[Tag] = frozenset({
    Tag.SHARP,
    Tag.HEAVY,
    Tag.LIGHT,
    Tag.BOUNCY,
    Tag.BREAKABLE,
    Tag.STICKY,
    Tag.REFLECTIVE,
    Tag.EXPLOSIVE,
    Tag.FLYING,
    Tag.WET,
})

# One-line gameplay descriptions for tag validation help text.
TAG_DESCRIPTIONS: dict[Tag, str] = {
    Tag.SHARP: "has a cutting edge or point. Swords, thorns, broken glass, claws",
    Tag.HEAVY: "dense and massive. Anvils, boulders, safes. Immovable by wind or pushing",
    Tag.LIGHT: "very low mass. Feathers, paper, balloons. Blown by WIND_SOURCE",
    Tag.BOUNCY: "elastic, high restitution. Rubber balls, springs, trampolines",
    Tag.BREAKABLE: "fragile, easily destroyed. Glass, pottery, eggshells",
    Tag.STICKY: "adhesive surface. Honey, tar, spider webs, glue. Slows nearby to 25% speed",
    Tag.REFLECTIVE: "smooth, mirror-like surface. Shields, mirrors, polished metal",
    Tag.EXPLOSIVE: "volatile, detonates under stress. Dynamite, grenades, gas canisters",
    Tag.FLYING: "defies gravity, hovers or flies. Birds, drones, balloons, ghosts, clouds",
    Tag.LIVING: "biological creature. Auto-derived from CREATURE category",
    Tag.WET: "damp or soaked. Amplifies ELECTRIC shock, freezes from COLD, resists fire",
    Tag.HOSTILE: "aggressive. Auto-derived from destroy behavior verb",
}

# Runtime tag contradictions — enforced by WorldMutations.apply_add_tag()
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
