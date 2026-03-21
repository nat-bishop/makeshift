from __future__ import annotations

from app.models.effects import Effect, EffectTarget, EffectType
from app.models.rules import InteractionRule
from app.models.tags import Tag

ALL_RULES: list[InteractionRule] = [
    # =========================================================================
    # FIRE / HEAT rules
    # =========================================================================
    # 1. HEAT_SOURCE + FLAMMABLE → IGNITE
    InteractionRule(
        rule_id="heat_flammable_ignite",
        name="Ignition",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.FLAMMABLE},
        priority=10,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.IGNITE,
                target=EffectTarget.B,
                damage_amount=10.0,
                tags_to_add=[Tag.HEAT_SOURCE, Tag.HOT],
                message="Ignited! Fire spreads.",
            ),
        ],
    ),
    # 2. HEAT_SOURCE + FROZEN → MELT
    InteractionRule(
        rule_id="heat_frozen_melt",
        name="Melting",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.FROZEN},
        priority=10,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.MELT,
                target=EffectTarget.B,
                tags_to_remove=[Tag.FROZEN, Tag.RIGID],
                tags_to_add=[Tag.LIQUID],
                message="The ice melts into water.",
            ),
        ],
    ),
    # 3. LIQUID + HEAT_SOURCE → EXTINGUISH
    InteractionRule(
        rule_id="liquid_heat_extinguish",
        name="Extinguish",
        tags_required_a={Tag.LIQUID},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=15,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.EXTINGUISH,
                target=EffectTarget.B,
                tags_to_remove=[Tag.HEAT_SOURCE, Tag.HOT],
                message="The flames are doused!",
            ),
            Effect(
                effect_type=EffectType.SPAWN,
                target=EffectTarget.B,
                spawn_description="steam cloud",
                message="Steam billows out.",
            ),
        ],
    ),
    # 4. SHARP + BREAKABLE → DAMAGE
    InteractionRule(
        rule_id="sharp_breakable_damage",
        name="Cut",
        tags_required_a={Tag.SHARP},
        tags_required_b={Tag.BREAKABLE},
        priority=8,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=25.0,
                message="Sliced! 25 damage.",
            ),
        ],
    ),
    # 5. COLD + LIQUID → FREEZE
    InteractionRule(
        rule_id="cold_liquid_freeze",
        name="Freeze Liquid",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.LIQUID},
        priority=10,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.FREEZE,
                target=EffectTarget.B,
                tags_to_add=[Tag.FROZEN, Tag.RIGID, Tag.SOLID],
                tags_to_remove=[Tag.LIQUID],
                message="The liquid freezes solid!",
            ),
        ],
    ),
    # 6. EXPLOSIVE + HEAT_SOURCE → DESTROY
    InteractionRule(
        rule_id="explosive_heat_detonate",
        name="Detonation",
        tags_required_a={Tag.EXPLOSIVE},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=20,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.DESTROY,
                target=EffectTarget.A,
                damage_amount=80.0,
                message="BOOM! Massive explosion!",
            ),
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=80.0,
                force_magnitude=500.0,
                message="Caught in the blast! 80 damage.",
            ),
        ],
    ),
    # 7. ELECTRIC + CONDUCTING → ELECTRIFY (cascade)
    InteractionRule(
        rule_id="electric_conducting_electrify",
        name="Electrical Conduction",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.CONDUCTING},
        priority=12,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.ELECTRIFY,
                target=EffectTarget.B,
                damage_amount=30.0,
                tags_to_add=[Tag.ELECTRIC],
                message="Electricity arcs through! 30 damage.",
            ),
        ],
    ),
    # 8. ELECTRIC + LIQUID → ELECTRIFY
    InteractionRule(
        rule_id="electric_liquid_electrify",
        name="Electrified Liquid",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.LIQUID},
        priority=15,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.ELECTRIFY,
                target=EffectTarget.B,
                damage_amount=30.0,
                tags_to_add=[Tag.ELECTRIC],
                message="The liquid becomes electrified! 30 damage.",
            ),
        ],
    ),
    # 9. ELECTRIC + INSULATING → NO EFFECT (blocks propagation)
    InteractionRule(
        rule_id="electric_insulating_block",
        name="Insulation Block",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.INSULATING},
        priority=20,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="The insulation blocks the electricity.",
            ),
        ],
    ),
    # 10. CORROSIVE + BREAKABLE → CORRODE
    InteractionRule(
        rule_id="corrosive_breakable_corrode",
        name="Corrosion",
        tags_required_a={Tag.CORROSIVE},
        tags_required_b={Tag.BREAKABLE},
        priority=8,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CORRODE,
                target=EffectTarget.B,
                damage_amount=15.0,
                message="Dissolving! 15 damage per second.",
            ),
        ],
    ),
    # 11. WIND_SOURCE + LIGHT → APPLY_FORCE (push)
    InteractionRule(
        rule_id="wind_light_push",
        name="Wind Push",
        tags_required_a={Tag.WIND_SOURCE},
        tags_required_b={Tag.LIGHT},
        priority=5,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=100.0,
                message="Blown away by the wind!",
            ),
        ],
    ),
    # 12. WIND_SOURCE + HEAT_SOURCE → fan flames (cascade)
    InteractionRule(
        rule_id="wind_heat_fan",
        name="Fan Flames",
        tags_required_a={Tag.WIND_SOURCE},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=8,
        bidirectional=False,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="The wind fans the flames, spreading fire further!",
            ),
        ],
    ),
    # 13. WIND_SOURCE + GAS → disperse
    InteractionRule(
        rule_id="wind_gas_disperse",
        name="Gas Dispersal",
        tags_required_a={Tag.WIND_SOURCE},
        tags_required_b={Tag.GAS},
        priority=6,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=150.0,
                message="The gas is dispersed by the wind.",
            ),
        ],
    ),
    # 14. MAGNETIC + CONDUCTING → attract
    InteractionRule(
        rule_id="magnetic_conducting_attract",
        name="Magnetic Attraction",
        tags_required_a={Tag.MAGNETIC},
        tags_required_b={Tag.CONDUCTING},
        priority=6,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=-80.0,
                message="Pulled by magnetic force!",
            ),
        ],
    ),
    # 15. TOXIC + LIVING → DAMAGE
    InteractionRule(
        rule_id="toxic_living_damage",
        name="Poison",
        tags_required_a={Tag.TOXIC},
        tags_required_b={Tag.LIVING},
        priority=10,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=10.0,
                message="Poisoned! 10 damage per second.",
            ),
        ],
    ),
    # 16. BOUNCY + HEAVY → reduced bounce
    InteractionRule(
        rule_id="bouncy_heavy_reduce",
        name="Heavy Bounce",
        tags_required_a={Tag.BOUNCY},
        tags_required_b={Tag.HEAVY},
        priority=4,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.A,
                message="Too heavy to bounce much. Bounce reduced.",
            ),
        ],
    ),
    # 17. STICKY + * → STICK (wildcard)
    InteractionRule(
        rule_id="sticky_wildcard_stick",
        name="Stick",
        tags_required_a={Tag.STICKY},
        tags_required_b=set(),  # wildcard
        priority=3,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.BOTH,
                message="Stuck together!",
            ),
        ],
    ),
    # 18. REFLECTIVE + HEAT_SOURCE → REFLECT
    InteractionRule(
        rule_id="reflective_heat_reflect",
        name="Heat Reflection",
        tags_required_a={Tag.REFLECTIVE},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=12,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=10.0,
                message="Heat reflected back to source!",
            ),
        ],
    ),
    # 19. COLD + MOLTEN → FREEZE (frozen lava = walkable)
    InteractionRule(
        rule_id="cold_molten_freeze",
        name="Solidify Lava",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.MOLTEN},
        priority=12,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.FREEZE,
                target=EffectTarget.B,
                tags_to_remove=[Tag.MOLTEN, Tag.LIQUID],
                tags_to_add=[Tag.SOLID, Tag.RIGID],
                message="The molten material solidifies into rock!",
            ),
        ],
    ),
    # 20. REFLECTIVE + ELECTRIC → reflect electricity
    InteractionRule(
        rule_id="reflective_electric_reflect",
        name="Electrical Reflection",
        tags_required_a={Tag.REFLECTIVE},
        tags_required_b={Tag.ELECTRIC},
        priority=14,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
                message="Electricity bounces off the reflective surface!",
            ),
        ],
    ),
    # =========================================================================
    # Additional rules (~30 more)
    # =========================================================================
    # 21. HEAVY + BREAKABLE → DAMAGE (crush)
    InteractionRule(
        rule_id="heavy_breakable_crush",
        name="Crush",
        tags_required_a={Tag.HEAVY},
        tags_required_b={Tag.BREAKABLE},
        priority=7,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=20.0,
                message="Crushed under the weight! 20 damage.",
            ),
        ],
    ),
    # 22. EXPLOSIVE + SHARP → shrapnel (area damage)
    InteractionRule(
        rule_id="explosive_sharp_shrapnel",
        name="Shrapnel",
        tags_required_a={Tag.EXPLOSIVE},
        tags_required_b={Tag.SHARP},
        priority=10,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.BOTH,
                damage_amount=40.0,
                force_magnitude=300.0,
                message="Shrapnel flies everywhere! 40 damage.",
            ),
        ],
    ),
    # 23. HEAT_SOURCE + HEAT_SOURCE → intensify
    InteractionRule(
        rule_id="heat_heat_intensify",
        name="Heat Intensification",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=5,
        bidirectional=False,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.BOTH,
                message="The heat intensifies!",
            ),
        ],
    ),
    # 24. CORROSIVE + RIGID → weaken
    InteractionRule(
        rule_id="corrosive_rigid_weaken",
        name="Structural Corrosion",
        tags_required_a={Tag.CORROSIVE},
        tags_required_b={Tag.RIGID},
        priority=7,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CORRODE,
                target=EffectTarget.B,
                damage_amount=10.0,
                message="The rigid structure corrodes. 10 damage.",
            ),
        ],
    ),
    # 25. MOLTEN + FLAMMABLE → IGNITE
    InteractionRule(
        rule_id="molten_flammable_ignite",
        name="Molten Ignition",
        tags_required_a={Tag.MOLTEN},
        tags_required_b={Tag.FLAMMABLE},
        priority=12,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.IGNITE,
                target=EffectTarget.B,
                damage_amount=15.0,
                tags_to_add=[Tag.HEAT_SOURCE, Tag.HOT],
                message="Molten contact ignites the material!",
            ),
        ],
    ),
    # 26. MOLTEN + LIVING → DAMAGE (severe burn)
    InteractionRule(
        rule_id="molten_living_burn",
        name="Molten Burn",
        tags_required_a={Tag.MOLTEN},
        tags_required_b={Tag.LIVING},
        priority=15,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=40.0,
                message="Severely burned by molten material! 40 damage.",
            ),
        ],
    ),
    # 27. HOT + LIVING → DAMAGE (minor burn)
    InteractionRule(
        rule_id="hot_living_burn",
        name="Heat Burn",
        tags_required_a={Tag.HOT},
        tags_required_b={Tag.LIVING},
        priority=8,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=5.0,
                message="Ouch! Burned! 5 damage.",
            ),
        ],
    ),
    # 28. FROZEN + BREAKABLE → shatter (extra damage)
    InteractionRule(
        rule_id="frozen_breakable_shatter",
        name="Shatter",
        tags_required_a={Tag.FROZEN},
        tags_required_b={Tag.BREAKABLE},
        priority=6,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=35.0,
                message="Frozen and shattered! 35 damage.",
            ),
        ],
    ),
    # 29. ELECTRIC + LIVING → DAMAGE (shock)
    InteractionRule(
        rule_id="electric_living_shock",
        name="Electric Shock",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.LIVING},
        priority=12,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
                message="Electrocuted! 30 damage.",
            ),
        ],
    ),
    # 30. WIND_SOURCE + FLOATING → launch
    InteractionRule(
        rule_id="wind_floating_launch",
        name="Wind Launch",
        tags_required_a={Tag.WIND_SOURCE},
        tags_required_b={Tag.FLOATING},
        priority=7,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=200.0,
                message="Launched skyward by the wind!",
            ),
        ],
    ),
    # 31. CORROSIVE + LIVING → poison damage
    InteractionRule(
        rule_id="corrosive_living_damage",
        name="Acid Burn",
        tags_required_a={Tag.CORROSIVE},
        tags_required_b={Tag.LIVING},
        priority=10,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=20.0,
                message="Acid burns! 20 damage.",
            ),
        ],
    ),
    # 32. MAGNETIC + MAGNETIC → attract each other
    InteractionRule(
        rule_id="magnetic_magnetic_attract",
        name="Magnetic Pair",
        tags_required_a={Tag.MAGNETIC},
        tags_required_b={Tag.MAGNETIC},
        priority=5,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.BOTH,
                force_magnitude=-60.0,
                message="Magnets snap together!",
            ),
        ],
    ),
    # 33. GLOWING + LIVING → attract attention (no damage, flavor)
    InteractionRule(
        rule_id="glowing_living_attract",
        name="Bioluminescent Lure",
        tags_required_a={Tag.GLOWING},
        tags_required_b={Tag.LIVING},
        priority=2,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=-30.0,
                message="Drawn to the light...",
            ),
        ],
    ),
    # 34. BOUNCY + RIGID → extra bounce
    InteractionRule(
        rule_id="bouncy_rigid_extrabounce",
        name="Hard Bounce",
        tags_required_a={Tag.BOUNCY},
        tags_required_b={Tag.RIGID},
        priority=4,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.A,
                force_magnitude=150.0,
                message="Bounces off the hard surface!",
            ),
        ],
    ),
    # 35. HEAT_SOURCE + LIQUID → evaporate (if not extinguish scenario)
    InteractionRule(
        rule_id="heat_liquid_evaporate",
        name="Evaporation",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.LIQUID},
        priority=8,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.TRANSFORM,
                target=EffectTarget.B,
                tags_to_remove=[Tag.LIQUID],
                tags_to_add=[Tag.GAS],
                message="The liquid evaporates into steam!",
            ),
        ],
    ),
    # 36. EXPLOSIVE + BREAKABLE → DESTROY
    InteractionRule(
        rule_id="explosive_breakable_destroy",
        name="Blast Destruction",
        tags_required_a={Tag.EXPLOSIVE},
        tags_required_b={Tag.BREAKABLE},
        priority=12,
        bidirectional=False,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.DESTROY,
                target=EffectTarget.B,
                damage_amount=80.0,
                force_magnitude=400.0,
                message="Obliterated by the explosion! 80 damage.",
            ),
        ],
    ),
    # 37. FROZEN + LIVING → cold damage
    InteractionRule(
        rule_id="frozen_living_cold",
        name="Frostbite",
        tags_required_a={Tag.FROZEN},
        tags_required_b={Tag.LIVING},
        priority=8,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=8.0,
                message="Frostbite! 8 damage.",
            ),
        ],
    ),
    # 38. SLIPPERY + HEAVY → slide
    InteractionRule(
        rule_id="slippery_heavy_slide",
        name="Heavy Slide",
        tags_required_a={Tag.SLIPPERY},
        tags_required_b={Tag.HEAVY},
        priority=4,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=120.0,
                message="Slides on the slippery surface!",
            ),
        ],
    ),
    # 39. WIND_SOURCE + FLAMMABLE → fan (spread fire faster)
    InteractionRule(
        rule_id="wind_flammable_fan",
        name="Wind-Fed Fire",
        tags_required_a={Tag.WIND_SOURCE},
        tags_required_b={Tag.FLAMMABLE},
        priority=6,
        bidirectional=False,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="Wind makes the material more combustible!",
            ),
        ],
    ),
    # 40. CORROSIVE + CONDUCTING → dissolve metal
    InteractionRule(
        rule_id="corrosive_conducting_dissolve",
        name="Metal Dissolution",
        tags_required_a={Tag.CORROSIVE},
        tags_required_b={Tag.CONDUCTING},
        priority=9,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CORRODE,
                target=EffectTarget.B,
                damage_amount=20.0,
                message="The acid dissolves the metal! 20 damage.",
            ),
        ],
    ),
    # 41. SHARP + LIVING → cut damage
    InteractionRule(
        rule_id="sharp_living_cut",
        name="Laceration",
        tags_required_a={Tag.SHARP},
        tags_required_b={Tag.LIVING},
        priority=9,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=25.0,
                message="Cut deeply! 25 damage.",
            ),
        ],
    ),
    # 42. FLOATING + HEAVY → cancel float (wildcard-like, specific)
    InteractionRule(
        rule_id="floating_heavy_cancel",
        name="Weight Anchor",
        tags_required_a={Tag.FLOATING},
        tags_required_b={Tag.HEAVY},
        priority=8,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.A,
                tags_to_remove=[Tag.FLOATING],
                message="Too heavy to float! Sinks down.",
            ),
        ],
    ),
    # 43. COLD + LIVING → slow
    InteractionRule(
        rule_id="cold_living_slow",
        name="Chill",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.LIVING},
        priority=6,
        bidirectional=True,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="Chilled to the bone. Movement slowed.",
            ),
        ],
    ),
    # 44. EXPLOSIVE + ELECTRIC → chain detonation
    InteractionRule(
        rule_id="explosive_electric_detonate",
        name="Electrical Detonation",
        tags_required_a={Tag.EXPLOSIVE},
        tags_required_b={Tag.ELECTRIC},
        priority=18,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.DESTROY,
                target=EffectTarget.A,
                damage_amount=80.0,
                force_magnitude=500.0,
                message="Electrical detonation! Massive blast!",
            ),
        ],
    ),
    # 45. FLEXIBLE + SHARP → resist cutting
    InteractionRule(
        rule_id="flexible_sharp_resist",
        name="Flex Resist",
        tags_required_a={Tag.FLEXIBLE},
        tags_required_b={Tag.SHARP},
        priority=9,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.A,
                damage_amount=10.0,
                message="Flexible material absorbs some of the cut. 10 damage.",
            ),
        ],
    ),
    # 46. LIVING + LIVING → no combat (neutral)
    InteractionRule(
        rule_id="living_living_neutral",
        name="Life Meets Life",
        tags_required_a={Tag.LIVING},
        tags_required_b={Tag.LIVING},
        priority=1,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.BOTH,
                message="Two living things regard each other.",
            ),
        ],
    ),
    # 47. HEAT_SOURCE + CONDUCTING → heat transfer
    InteractionRule(
        rule_id="heat_conducting_transfer",
        name="Heat Conduction",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.CONDUCTING},
        priority=8,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tags_to_add=[Tag.HOT],
                message="Heat conducts through the material!",
            ),
        ],
    ),
    # 48. COLD + CONDUCTING → cold transfer
    InteractionRule(
        rule_id="cold_conducting_transfer",
        name="Cold Conduction",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.CONDUCTING},
        priority=8,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tags_to_add=[Tag.COLD],
                message="Cold spreads through the conductor!",
            ),
        ],
    ),
    # 49. INSULATING + HEAT_SOURCE → block heat
    InteractionRule(
        rule_id="insulating_heat_block",
        name="Heat Insulation",
        tags_required_a={Tag.INSULATING},
        tags_required_b={Tag.HEAT_SOURCE},
        priority=14,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="Insulation blocks the heat transfer.",
            ),
        ],
    ),
    # 50. INSULATING + COLD → block cold
    InteractionRule(
        rule_id="insulating_cold_block",
        name="Cold Insulation",
        tags_required_a={Tag.INSULATING},
        tags_required_b={Tag.COLD},
        priority=14,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="Insulation blocks the cold transfer.",
            ),
        ],
    ),
    # 51. MOLTEN + BREAKABLE → DESTROY
    InteractionRule(
        rule_id="molten_breakable_destroy",
        name="Molten Destruction",
        tags_required_a={Tag.MOLTEN},
        tags_required_b={Tag.BREAKABLE},
        priority=12,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DESTROY,
                target=EffectTarget.B,
                damage_amount=50.0,
                message="Melted by molten material! 50 damage.",
            ),
        ],
    ),
    # 52. TOXIC + GAS → toxic cloud (spreads)
    InteractionRule(
        rule_id="toxic_gas_cloud",
        name="Toxic Cloud",
        tags_required_a={Tag.TOXIC},
        tags_required_b={Tag.GAS},
        priority=8,
        bidirectional=True,
        cascade_eligible=True,
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tags_to_add=[Tag.TOXIC],
                message="A toxic cloud forms and spreads!",
            ),
        ],
    ),
    # 53. CLIMBABLE + * → enable climb (wildcard)
    InteractionRule(
        rule_id="climbable_wildcard",
        name="Climbable Surface",
        tags_required_a={Tag.CLIMBABLE},
        tags_required_b=set(),
        priority=2,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.CHANGE_PROPERTY,
                target=EffectTarget.B,
                message="A climbable surface!",
            ),
        ],
    ),
    # 54. HEAT_SOURCE + INSULATING → blocked (higher priority version)
    # Already covered by rule 49, this ensures reverse direction
    # 55. ELECTRIC + BREAKABLE → damage
    InteractionRule(
        rule_id="electric_breakable_damage",
        name="Electric Damage",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.BREAKABLE},
        priority=10,
        bidirectional=False,
        cascade_eligible=False,
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
                message="Electrical surge! 30 damage.",
            ),
        ],
    ),
]
