"""Trait derivation: substance + element + explicit tags → internal traits + profiles."""

from __future__ import annotations

from app.models.substances import (
    ELEMENT_PROFILE_OVERRIDES,
    ELEMENT_TRAITS,
    SUBSTANCE_AUTO_TRAITS,
    SUBSTANCE_PROFILES,
    Element,
    Substance,
    SubstanceProfile,
    SubstanceState,
)
from app.models.tags import Category, Tag


def derive_traits(
    substance: Substance,
    element: Element | None,
    tags: list[Tag],
    behavior_verbs: list[str] | None = None,
    categories: list[Category] | None = None,
) -> list[Tag]:
    """Compute full internal trait set from substance + element + tags + behaviors + categories."""
    trait_set: set[Tag] = set()

    # Substance auto-traits
    trait_set.update(SUBSTANCE_AUTO_TRAITS.get(substance, []))

    # Element traits
    if element is not None:
        trait_set.update(ELEMENT_TRAITS.get(element, []))

    # Explicit tags (LLM-chosen)
    trait_set.update(tags)

    # Behavior-derived: destroy verb → HOSTILE
    if behavior_verbs and "destroy" in behavior_verbs:
        trait_set.add(Tag.HOSTILE)

    # Category-derived: CREATURE → LIVING
    if categories and Category.CREATURE in categories:
        trait_set.add(Tag.LIVING)

    return sorted(trait_set, key=lambda t: t.value)


# State-derived physics defaults: (gravity, damping)
_STATE_DEFAULTS: dict[SubstanceState, tuple[float, float]] = {
    SubstanceState.SOLID: (1.0, 0.5),
    SubstanceState.LIQUID: (1.0, 2.0),
    SubstanceState.GAS: (-0.2, 4.0),
    SubstanceState.ENERGY: (0.0, 0.0),
}


def resolve_profile(
    substance: Substance,
    element: Element | None,
    tags: list[Tag],
) -> SubstanceProfile:
    """Build the final substance profile: base → element overrides → tag modifiers."""
    base = SUBSTANCE_PROFILES[substance]
    # Copy mutable values
    mass = base.mass
    durability = base.durability
    friction = base.friction
    conductivity = base.conductivity
    burn_rate = base.burn_rate
    specific_heat = base.specific_heat
    heat_output = base.heat_output
    state = base.state

    # State-derived defaults
    gravity, damping = _STATE_DEFAULTS[state]
    bounce = 0.0

    # Element profile overrides (use max of base vs override)
    if element is not None:
        overrides = ELEMENT_PROFILE_OVERRIDES.get(element, {})
        if "heat_output" in overrides:
            heat_output = max(heat_output, overrides["heat_output"])
        if "conductivity" in overrides:
            conductivity = max(conductivity, overrides["conductivity"])

    # Tag profile modifiers
    tag_set = set(tags)
    if Tag.HEAVY in tag_set:
        mass += 5.0
        friction = max(friction, 0.7)
    if Tag.LIGHT in tag_set:
        mass *= 0.15
        damping = 1.5
    if Tag.BREAKABLE in tag_set:
        durability *= 0.4
    if Tag.BOUNCY in tag_set:
        bounce = 0.9
        friction = min(friction, 0.2)
    if Tag.STICKY in tag_set:
        friction = max(friction, 2.0)
        bounce = 0.0
    if Tag.FLYING in tag_set:
        gravity = 0.0
        damping = 2.0

    return SubstanceProfile(
        mass=mass,
        durability=durability,
        friction=friction,
        conductivity=conductivity,
        burn_rate=burn_rate,
        specific_heat=specific_heat,
        heat_output=heat_output,
        state=state,
        gravity=gravity,
        bounce=bounce,
        damping=damping,
    )


def compute_combat_profile(profile: SubstanceProfile) -> dict[str, float]:
    """Pre-compute combat values from a substance profile."""
    return {
        "melee_damage": clamp(25.0 * profile.mass / 1.5, 10.0, 60.0),
        "crush_damage": clamp(20.0 * profile.mass / 5.0, 10.0, 60.0),
        "fire_dps_coefficient": 10.0 * profile.heat_output,
        "conductivity": profile.conductivity,
        "mass": profile.mass,
    }


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
