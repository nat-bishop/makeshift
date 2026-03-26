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
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.HEAT_SOURCE,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.HOT,
            ),
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=10.0,
                tick_interval=1.0,
                tick_duration=5.0,
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
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.FROZEN,
            ),
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.RIGID,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.LIQUID,
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
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.HEAT_SOURCE,
            ),
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.HOT,
                message="The flames are doused!",
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
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.FROZEN,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.RIGID,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.SOLID,
            ),
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.LIQUID,
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.A,
                damage_amount=99999.0,
                message="BOOM! Massive explosion!",
            ),
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=80.0,
            ),
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
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
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.ELECTRIC,
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
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.ELECTRIC,
                message="The liquid becomes electrified! 30 damage.",
            ),
        ],
    ),
    # 9. CORROSIVE + BREAKABLE → CORRODE
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=15.0,
                tick_interval=1.0,
                tick_duration=3.0,
                message="Dissolving! 15 damage per second.",
            ),
        ],
    ),
    # 10. WIND_SOURCE + LIGHT → APPLY_FORCE (push)
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
    # 11. WIND_SOURCE + GAS → disperse
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
    # 12. MAGNETIC + CONDUCTING → attract
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
    # 13. TOXIC + LIVING → DAMAGE
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
    # 14. REFLECTIVE + HEAT_SOURCE → REFLECT
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
    # 15. COLD + MOLTEN → FREEZE (frozen lava = walkable)
    InteractionRule(
        rule_id="cold_molten_freeze",
        name="Solidify Lava",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.MOLTEN},
        priority=12,
        bidirectional=True,
        cascade_eligible=False,
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.SOLID,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.RIGID,
            ),
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.MOLTEN,
            ),
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.LIQUID,
                message="The molten material solidifies into rock!",
            ),
        ],
    ),
    # 16. REFLECTIVE + ELECTRIC → reflect electricity
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
    # 17. HEAVY + BREAKABLE → DAMAGE (crush)
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
    # 18. EXPLOSIVE + SHARP → shrapnel (area damage)
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
            ),
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.BOTH,
                force_magnitude=300.0,
                message="Shrapnel flies everywhere! 40 damage.",
            ),
        ],
    ),
    # 19. CORROSIVE + RIGID → weaken
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=10.0,
                tick_interval=1.0,
                tick_duration=3.0,
                message="The rigid structure corrodes. 10 damage.",
            ),
        ],
    ),
    # 20. MOLTEN + FLAMMABLE → IGNITE
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
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.HEAT_SOURCE,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.HOT,
            ),
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=15.0,
                tick_interval=1.0,
                tick_duration=5.0,
                message="Molten contact ignites the material!",
            ),
        ],
    ),
    # 21. MOLTEN + LIVING → DAMAGE (severe burn)
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
    # 22. HOT + LIVING → DAMAGE (minor burn)
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
    # 23. FROZEN + BREAKABLE → shatter (extra damage)
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
    # 24. ELECTRIC + LIVING → DAMAGE (shock)
    InteractionRule(
        rule_id="electric_living_shock",
        name="Electric Shock",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.LIVING},
        priority=12,
        bidirectional=True,
        cascade_eligible=False,
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=30.0,
                message="Electrocuted! 30 damage.",
            ),
        ],
    ),
    # 25. WIND_SOURCE + FLOATING → launch
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
    # 26. CORROSIVE + LIVING → poison damage
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
    # 27. MAGNETIC + MAGNETIC → attract each other
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
    # 28. GLOWING + LIVING → attract attention (no damage, flavor)
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
    # 29. BOUNCY + RIGID → extra bounce
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
    # 30. HEAT_SOURCE + LIQUID → evaporate (if not extinguish scenario)
    InteractionRule(
        rule_id="heat_liquid_evaporate",
        name="Evaporation",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.LIQUID},
        priority=8,
        bidirectional=False,
        cascade_eligible=False,
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.REMOVE_TAG,
                target=EffectTarget.B,
                tag=Tag.LIQUID,
            ),
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.GAS,
                message="The liquid evaporates into steam!",
            ),
        ],
    ),
    # 31. EXPLOSIVE + BREAKABLE → DESTROY
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=99999.0,
            ),
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.B,
                force_magnitude=400.0,
                message="Obliterated by the explosion!",
            ),
        ],
    ),
    # 32. FROZEN + LIVING → cold damage
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
    # 33. SLIPPERY + HEAVY → slide
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
    # 34. CORROSIVE + CONDUCTING → dissolve metal
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=20.0,
                tick_interval=1.0,
                tick_duration=3.0,
                message="The acid dissolves the metal! 20 damage.",
            ),
        ],
    ),
    # 35. SHARP + LIVING → cut damage
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
    # 36. FLOATING + HEAVY → cancel float
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
                tag=Tag.FLOATING,
                message="Too heavy to float! Sinks down.",
            ),
        ],
    ),
    # 37. EXPLOSIVE + ELECTRIC → chain detonation
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.A,
                damage_amount=99999.0,
            ),
            Effect(
                effect_type=EffectType.APPLY_FORCE,
                target=EffectTarget.A,
                force_magnitude=500.0,
                message="Electrical detonation! Massive blast!",
            ),
        ],
    ),
    # 38. FLEXIBLE + SHARP → resist cutting
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
    # 39. HEAT_SOURCE + CONDUCTING → heat transfer
    InteractionRule(
        rule_id="heat_conducting_transfer",
        name="Heat Conduction",
        tags_required_a={Tag.HEAT_SOURCE},
        tags_required_b={Tag.CONDUCTING},
        priority=8,
        bidirectional=True,
        cascade_eligible=True,
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.HOT,
                message="Heat conducts through the material!",
            ),
        ],
    ),
    # 40. COLD + CONDUCTING → cold transfer
    InteractionRule(
        rule_id="cold_conducting_transfer",
        name="Cold Conduction",
        tags_required_a={Tag.COLD},
        tags_required_b={Tag.CONDUCTING},
        priority=8,
        bidirectional=True,
        cascade_eligible=True,
        tags_blocked_by={Tag.INSULATING},
        effects=[
            Effect(
                effect_type=EffectType.ADD_TAG,
                target=EffectTarget.B,
                tag=Tag.COLD,
                message="Cold spreads through the conductor!",
            ),
        ],
    ),
    # 41. MOLTEN + BREAKABLE → DESTROY
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
                effect_type=EffectType.DAMAGE,
                target=EffectTarget.B,
                damage_amount=99999.0,
                message="Melted by molten material!",
            ),
        ],
    ),
    # 42. TOXIC + GAS → toxic cloud (spreads)
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
                tag=Tag.TOXIC,
                message="A toxic cloud forms and spreads!",
            ),
        ],
    ),
    # 43. ELECTRIC + BREAKABLE → damage
    InteractionRule(
        rule_id="electric_breakable_damage",
        name="Electric Damage",
        tags_required_a={Tag.ELECTRIC},
        tags_required_b={Tag.BREAKABLE},
        priority=10,
        bidirectional=False,
        cascade_eligible=False,
        tags_blocked_by={Tag.INSULATING},
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
