from enum import StrEnum

from pydantic import BaseModel

from app.models.tags import Tag


class Substance(StrEnum):
    METAL = "metal"
    WOOD = "wood"
    STONE = "stone"
    GLASS = "glass"
    RUBBER = "rubber"
    BONE = "bone"
    CERAMIC = "ceramic"
    CLOTH = "cloth"
    WATER = "water"
    OIL = "oil"
    SLIME = "slime"
    ICE = "ice"
    LAVA = "lava"
    FIRE = "fire"
    SMOKE = "smoke"
    FLESH = "flesh"


class SubstanceState(StrEnum):
    SOLID = "solid"
    LIQUID = "liquid"
    GAS = "gas"
    ENERGY = "energy"


class SubstanceProfile(BaseModel):
    mass: float
    durability: float
    friction: float
    conductivity: float
    burn_rate: float
    specific_heat: float
    heat_output: float
    state: SubstanceState
    # Physics fields resolved later (not part of base substance data)
    gravity: float = -1.0  # -1 = use state default
    bounce: float = 0.0
    damping: float = -1.0  # -1 = use state default


SUBSTANCE_PROFILES: dict[Substance, SubstanceProfile] = {
    Substance.METAL: SubstanceProfile(
        mass=3.0, durability=250, friction=0.6, conductivity=0.9,
        burn_rate=0.0, specific_heat=0.3, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.WOOD: SubstanceProfile(
        mass=1.0, durability=120, friction=0.5, conductivity=0.05,
        burn_rate=0.8, specific_heat=0.5, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.STONE: SubstanceProfile(
        mass=4.0, durability=300, friction=0.7, conductivity=0.1,
        burn_rate=0.0, specific_heat=0.8, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.GLASS: SubstanceProfile(
        mass=1.5, durability=40, friction=0.3, conductivity=0.05,
        burn_rate=0.0, specific_heat=0.4, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.RUBBER: SubstanceProfile(
        mass=0.8, durability=100, friction=0.8, conductivity=0.01,
        burn_rate=0.3, specific_heat=0.6, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.BONE: SubstanceProfile(
        mass=1.8, durability=150, friction=0.5, conductivity=0.05,
        burn_rate=0.1, specific_heat=0.5, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.CERAMIC: SubstanceProfile(
        mass=2.0, durability=60, friction=0.6, conductivity=0.02,
        burn_rate=0.0, specific_heat=0.7, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.CLOTH: SubstanceProfile(
        mass=0.3, durability=40, friction=0.4, conductivity=0.03,
        burn_rate=0.9, specific_heat=0.3, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.WATER: SubstanceProfile(
        mass=0.8, durability=9999, friction=0.0, conductivity=0.7,
        burn_rate=0.0, specific_heat=1.0, heat_output=0.0, state=SubstanceState.LIQUID,
    ),
    Substance.OIL: SubstanceProfile(
        mass=0.6, durability=9999, friction=0.05, conductivity=0.01,
        burn_rate=1.0, specific_heat=0.4, heat_output=0.0, state=SubstanceState.LIQUID,
    ),
    Substance.SLIME: SubstanceProfile(
        mass=1.2, durability=9999, friction=2.0, conductivity=0.1,
        burn_rate=0.0, specific_heat=0.6, heat_output=0.0, state=SubstanceState.LIQUID,
    ),
    Substance.ICE: SubstanceProfile(
        mass=2.0, durability=80, friction=0.05, conductivity=0.15,
        burn_rate=0.0, specific_heat=0.2, heat_output=0.0, state=SubstanceState.SOLID,
    ),
    Substance.LAVA: SubstanceProfile(
        mass=5.0, durability=9999, friction=0.9, conductivity=0.3,
        burn_rate=0.0, specific_heat=0.9, heat_output=3.0, state=SubstanceState.LIQUID,
    ),
    Substance.FIRE: SubstanceProfile(
        mass=0.01, durability=30, friction=0.0, conductivity=0.2,
        burn_rate=0.0, specific_heat=0.1, heat_output=1.5, state=SubstanceState.ENERGY,
    ),
    Substance.SMOKE: SubstanceProfile(
        mass=0.01, durability=9999, friction=0.0, conductivity=0.0,
        burn_rate=0.0, specific_heat=0.1, heat_output=0.0, state=SubstanceState.GAS,
    ),
    Substance.FLESH: SubstanceProfile(
        mass=1.5, durability=150, friction=0.5, conductivity=0.3,
        burn_rate=0.2, specific_heat=0.7, heat_output=0.0, state=SubstanceState.SOLID,
    ),
}

SUBSTANCE_AUTO_TRAITS: dict[Substance, list[Tag]] = {
    Substance.METAL: [Tag.METALLIC, Tag.RIGID],
    Substance.WOOD: [Tag.FLAMMABLE],
    Substance.STONE: [Tag.RIGID, Tag.HEAVY],
    Substance.GLASS: [Tag.BREAKABLE, Tag.REFLECTIVE],
    Substance.RUBBER: [Tag.BOUNCY, Tag.INSULATING],
    Substance.BONE: [Tag.RIGID],
    Substance.CERAMIC: [Tag.BREAKABLE, Tag.INSULATING],
    Substance.CLOTH: [Tag.FLAMMABLE, Tag.LIGHT],
    Substance.WATER: [Tag.LIQUID, Tag.WET],
    Substance.OIL: [Tag.LIQUID, Tag.FLAMMABLE],
    Substance.SLIME: [Tag.LIQUID, Tag.STICKY, Tag.TOXIC],
    Substance.ICE: [Tag.FROZEN, Tag.RIGID, Tag.COLD, Tag.BRITTLE],
    Substance.LAVA: [Tag.MOLTEN, Tag.LIQUID, Tag.HEAT_SOURCE],
    Substance.FIRE: [Tag.GAS, Tag.HEAT_SOURCE, Tag.HOT],
    Substance.SMOKE: [Tag.GAS, Tag.LIGHT],
    Substance.FLESH: [],
}


class Element(StrEnum):
    BURNING = "burning"
    ELECTRIC = "electric"
    MAGNETIC = "magnetic"
    FREEZING = "freezing"
    ACIDIC = "acidic"
    TOXIC = "toxic"
    WINDY = "windy"


ELEMENT_TRAITS: dict[Element, list[Tag]] = {
    Element.BURNING: [Tag.HEAT_SOURCE, Tag.HOT],
    Element.ELECTRIC: [Tag.ELECTRIC],
    Element.MAGNETIC: [Tag.MAGNETIC],
    Element.FREEZING: [Tag.COLD],
    Element.ACIDIC: [Tag.ACIDIC],
    Element.TOXIC: [Tag.TOXIC],
    Element.WINDY: [Tag.WIND_SOURCE],
}

# Element overrides applied to the substance profile
ELEMENT_PROFILE_OVERRIDES: dict[Element, dict[str, float]] = {
    Element.BURNING: {"heat_output": 1.0},  # max(base, 1.0) applied in resolve_profile
    Element.ELECTRIC: {"conductivity": 0.5},  # max(base, 0.5) applied in resolve_profile
}
