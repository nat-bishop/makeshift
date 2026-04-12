"""Data-driven question definitions for all LLM call pipelines.

Creation and creature questions are all defined here as Question
instances. Edit this file to add, remove, or tweak object properties during
playtesting. Gate conditions control conditional fan-out (e.g. speed
only fires when autonomous=true).
"""

from __future__ import annotations

from app.creator.question_graph import Gate, Question

# ---- Reusable gate conditions ----

GATE_AUTONOMOUS = Gate("autonomous", lambda v: bool(v))
GATE_DESTRUCTIBLE = Gate("durability", lambda v: int(v) < 6)  # type: ignore[call-overload]

# ---- Creation questions ----
# All fired via run_questions() after name generation resolves.
# Prompts use {description} placeholder (the player's original input).

CREATION_QUESTIONS: list[Question] = [
    # Physics — open-ended numeric (instructions + bare name)
    Question(
        "mass_kg",
        "{description}",
        "float",
        0.001,
        100000,
        1.0,
        instructions=(
            "Estimate the real-world mass of the given object in kilograms. Return only a number."
        ),
    ),
    Question(
        "height_cm",
        "{description}",
        "int",
        1,
        5000,
        30,
        instructions=(
            "Estimate the real-world height of the given object in centimeters. "
            "Examples: coin=2, apple=8, cat=25, chair=90, person=175, tree=800, mountain=5000. "
            "Return only an integer."
        ),
    ),
    Question(
        "surface",
        "{description}",
        "choice",
        default="normal",
        instructions=(
            "Classify this object's surface texture. "
            "slick=ice/oil/glass, normal=wood/metal/stone/fabric, sticky=tar/glue/resin."
        ),
        choices=("slick", "normal", "sticky"),
        choice_map=(("slick", 0), ("normal", 1), ("sticky", 2)),
    ),
    Question(
        "bounce",
        "{description}",
        "int",
        0,
        100,
        10,
        instructions=(
            "Rate the bounciness of the given object from 0 to 100. "
            "0=no bounce (sand, mud), 10=minimal (rock, wood), "
            "30=soft cushion (pillow, mattress), 50=moderate (tennis ball), "
            "80=very bouncy (rubber ball, bouncy ball), 100=maximum bounce."
        ),
    ),
    Question(
        "gravity",
        "{description}",
        "int",
        instructions=(
            "Rate how the given object falls when unsupported. "
            "0=floats upward (balloon, helium), 10=drifts slowly (feather, smoke), "
            "50=falls normally (person, ball), 65=falls heavily (anvil, boulder), "
            "75=very heavy fall (lead block). "
            "Immovable objects that sit on the ground use 50-65, not 100."
        ),
    ),
    # Durability
    Question(
        "durability",
        "{description}",
        "choice",
        default="normal",
        instructions=(
            "How easily does this object break? "
            "soft=crumbles on touch (paper, balloon), "
            "weak=breaks from a drop (glass, ice), "
            "normal=survives casual handling (wood, campfire, plastic), "
            "solid=resists strong force (iron, brick), "
            "strong=requires extreme force (steel, thick stone), "
            "elite=nearly indestructible (tank, vault), "
            "permanent=cannot be destroyed (mountain, bedrock)."
        ),
        choices=("soft", "weak", "normal", "solid", "strong", "elite", "permanent"),
        choice_map=(
            ("soft", 0),
            ("weak", 1),
            ("normal", 2),
            ("solid", 3),
            ("strong", 4),
            ("elite", 5),
            ("permanent", 6),
        ),
    ),
    # Autonomous
    Question(
        "autonomous",
        "{description}",
        "choice",
        default="no",
        instructions=(
            "Does this object move and act on its own? "
            "Animals, creatures, monsters, robots, and people are autonomous. "
            "Plants, tools, furniture, and terrain are not."
        ),
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    # Gated on autonomous=true
    Question(
        "speed",
        "{description}",
        "choice",
        default="normal",
        gates=(GATE_AUTONOMOUS,),
        instructions=(
            "Rate this creature's movement speed. "
            "crawl=snail/turtle, slow=zombie/slug, normal=person/dog, "
            "fast=horse/wolf, rapid=cheetah/falcon."
        ),
        choices=("crawl", "slow", "normal", "fast", "rapid"),
        choice_map=(("crawl", 0), ("slow", 1), ("normal", 2), ("fast", 3), ("rapid", 4)),
    ),
    Question(
        "affordance",
        "{description}",
        "choice",
        default="none",
        instructions=(
            "In a 2D game, how can a player physically interact with this object? "
            "carry=pick up and hold (sword, bottle, ball, cat, small items), "
            "ride=sit on top and move (horse, car, boat), "
            "scale=climb up it (ladder, tree, wall), "
            "none=too heavy/large/immovable (boulder, lava, mountain)."
        ),
        choices=("carry", "ride", "scale", "none"),
        choice_map=(("carry", 0), ("ride", 1), ("scale", 2), ("none", 3)),
    ),
    # ---- State properties (initial + susceptible) ----
    # Initial states — does this object spawn with these states?
    Question(
        "initially_burning",
        "{description}",
        "choice",
        default="no",
        instructions="Does this object produce fire or heat?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_frozen",
        "{description}",
        "choice",
        default="no",
        instructions="Is this object frozen or ice-cold?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_wet",
        "{description}",
        "choice",
        default="no",
        instructions="Is this object wet or made of water or liquid?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_electrified",
        "{description}",
        "choice",
        default="no",
        instructions="Does this object produce electricity?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    # Susceptible states — can these states spread to this object?
    Question(
        "catches_fire",
        "{description}",
        "choice",
        default="no",
        instructions="Can this object catch fire from a nearby burning object?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "can_freeze",
        "{description}",
        "choice",
        default="no",
        instructions="Can this object freeze from contact with something frozen?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "gets_wet",
        "{description}",
        "choice",
        default="no",
        instructions="Can this object get wet from a nearby wet object?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "conducts_electricity",
        "{description}",
        "choice",
        default="no",
        instructions="Can this object conduct electricity from an electrified object?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
]

# Text questions — also Question instances with gates

NAME_QUESTION = Question(
    "name",
    "Shorten this to a 1-5 word object name: {description}. "
    "Keep the same words where possible. Do not rename or rephrase. "
    "Reply with ONLY the name.",
    "text",
    max_tokens=50,
    default="Object",
)

VISUAL_QUESTION = Question(
    "visual_description",
    "Describe '{description}' as a mixed media paper collage — cut from magazines, "
    "encyclopedias, or children's books and taped together. What paper/cardboard pieces "
    "make up its shape? What colors and textures are visible? "
    "Max 2 sentences. Reply with ONLY the description.",
    "text",
    max_tokens=250,
    default="a {description} made from cut paper and cardboard",
)

DESTRUCTION_QUESTION = Question(
    "destruction_result_name",
    "When {description} is destroyed, what remains? "
    "Reply with a 1-3 word name for the debris/remains, or 'nothing' if it vanishes completely. "
    "Examples: wooden sword -> splinters, glass bottle -> glass shards, balloon -> nothing, "
    "ice block -> puddle, robot -> scrap metal",
    "text",
    max_tokens=30,
    default="nothing",
    gates=(GATE_DESTRUCTIBLE,),
)

# Combined list for the creation pipeline (name is handled separately)
ALL_CREATION_QUESTIONS: list[Question] = [
    *CREATION_QUESTIONS,
    VISUAL_QUESTION,
    DESTRUCTION_QUESTION,
]
