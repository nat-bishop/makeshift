"""Data-driven question definitions for all LLM call pipelines.

Creation, pairwise, and creature questions are all defined here as Question
instances. Edit this file to add, remove, or tweak object properties during
playtesting. Gate conditions control conditional fan-out (e.g. field_range_cm
only fires when has_field=true).
"""

from __future__ import annotations

from app.creator.question_graph import Gate, Question

# ---- Reusable gate conditions ----

GATE_HAS_FIELD = Gate("has_field", lambda v: bool(v))
GATE_DESTRUCTIBLE = Gate("durability", lambda v: int(v) < 6)

# ---- Creation questions ----
# All fired via run_questions() after name generation resolves.
# Prompts use {name} and {description} placeholders.

CREATION_QUESTIONS: list[Question] = [
    # Physics
    Question(
        "mass_kg",
        "How heavy is {name} in kg? "
        "(ant=0.001, feather=0.01, ball=0.2, torch=0.5, sword=1.5, chair=8, "
        "human=70, boulder=100, horse=400, car=1500, mountain=50000)",
        "float",
        0.001,
        100000,
        1.0,
    ),
    Question(
        "height_cm",
        "How tall is {name} in cm? "
        "(ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800)",
        "int",
        1,
        5000,
        30,
    ),
    Question(
        "surface",
        "What surface does {name} have? "
        "0=slippery(ice, oil, wet) 1=normal(wood, metal, stone, rubber) "
        "2=sticky(glue, tar, tape, gum)",
        "int",
        0,
        2,
        1,
    ),
    Question(
        "bounce",
        "How bouncy is {name} 0-100? "
        "(clay=0, brick=5, animal=10, wood=20, tennis ball=70, super ball=99)",
        "int",
        0,
        100,
        10,
    ),
    Question(
        "gravity",
        "How does {name} fall when unsupported? "
        "0=floats upward(balloon, helium) 25=drifts slowly(feather, smoke) "
        "50=falls normally(rock, sword) 75=falls heavily(lead, anvil) "
        "100=slams down(neutron star)",
        "int",
    ),
    # Gate trigger
    Question(
        "has_field",
        "Does {name} affect nearby things without touching "
        "(heat, cold, magnetism, toxin)? "
        "(torch=1, campfire=1, magnet=1, sword=0, rock=0) 0=no 1=yes",
        "bool",
    ),
    # Gated on has_field=true
    Question(
        "field_range_cm",
        "If {name} has area effect, range in cm? "
        "(candle=50, campfire=200, bonfire=400, volcano=500)",
        "int",
        10,
        500,
        100,
        gates=(GATE_HAS_FIELD,),
    ),
    # Durability (single scale replaces hp + armor + indestructible)
    Question(
        "durability",
        "How durable is {name}? "
        "0=fragile(paper, balloon) 1=weak(glass, web) 2=normal(wood, flesh) "
        "3=tough(stone, bone) 4=hardy(steel, diamond) "
        "5=fortified(castle wall) 6=indestructible(mountain)",
        "int",
        0,
        6,
        2,
    ),
    # Other unconditional
    Question(
        "autonomous",
        "Does {name} move and act on its own? "
        "(rock=0, sword=0, horse=1, zombie=1, cat=1, robot=1) 0=no 1=yes",
        "bool",
    ),
    Question(
        "affordance",
        "When a player interacts with {name}: "
        "0=pick up and carry 1=ride on top 2=climb it 3=can't interact "
        "(sword=0, horse=1, ladder=2, zombie=3, boulder=3, fire=3)",
        "int",
        0,
        3,
        3,
    ),
]

# Text questions — also Question instances with gates

NAME_QUESTION = Question(
    "name",
    "Give a 1-3 word game object name for: {description}. Reply with ONLY the name, nothing else.",
    "text",
    max_tokens=8,
    default="Object",
)

VISUAL_QUESTION = Question(
    "visual_description",
    "Describe the appearance of '{name}' ({description}) for a 2D sprite artist. "
    "Shape, material, colors, distinctive features. "
    "Max 2 sentences. Reply with ONLY the description.",
    "text",
    max_tokens=40,
    default="a {description}",
)

DESTRUCTION_QUESTION = Question(
    "destruction_result_name",
    "When {name} is destroyed, what remains? "
    "Reply with a 1-3 word name for the debris/remains, or 'nothing' if it vanishes completely. "
    "Examples: wooden sword -> splinters, glass bottle -> glass shards, balloon -> nothing, "
    "ice block -> puddle, robot -> scrap metal",
    "text",
    max_tokens=8,
    default="nothing",
    gates=(GATE_DESTRUCTIBLE,),
)

# Combined list for the creation pipeline (name is handled separately)
ALL_CREATION_QUESTIONS: list[Question] = [
    *CREATION_QUESTIONS,
    VISUAL_QUESTION,
    DESTRUCTION_QUESTION,
]
