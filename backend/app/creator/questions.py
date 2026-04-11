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
# Prompts use {name} placeholder (the LLM-generated name).

CREATION_QUESTIONS: list[Question] = [
    # Physics — open-ended numeric (instructions + bare name)
    Question(
        "mass_kg",
        "{name}",
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
        "{name}",
        "int",
        1,
        5000,
        30,
        instructions=(
            "Estimate the real-world height of the given object in centimeters. "
            "Return only an integer."
        ),
    ),
    Question(
        "surface",
        "{name}",
        "choice",
        default="normal",
        instructions="Classify this object's surface texture.",
        choices=("slick", "normal", "sticky"),
        choice_map=(("slick", 0), ("normal", 1), ("sticky", 2)),
    ),
    Question(
        "bounce",
        "{name}",
        "int",
        0,
        100,
        10,
        instructions=(
            "Rate the bounciness of the given object from 0 to 100. "
            "0=no bounce, 50=moderate, 100=maximum bounce. "
            "Return only an integer."
        ),
    ),
    Question(
        "gravity",
        "{name}",
        "int",
        instructions=(
            "Rate how the given object falls when unsupported. "
            "0=floats upward, 25=drifts slowly, 50=falls normally, "
            "75=falls heavily, 100=slams down instantly. Return only an integer."
        ),
    ),
    # Durability
    Question(
        "durability",
        "{name}",
        "choice",
        default="normal",
        instructions=(
            "How easily does this object break? "
            "soft=crumbles on touch, weak=breaks from a drop, "
            "normal=survives casual handling, solid=resists strong force, "
            "strong=requires extreme force to damage, "
            "iron=nearly indestructible, permanent=cannot be destroyed."
        ),
        choices=("soft", "weak", "normal", "solid", "strong", "iron", "permanent"),
        choice_map=(
            ("soft", 0),
            ("weak", 1),
            ("normal", 2),
            ("solid", 3),
            ("strong", 4),
            ("iron", 5),
            ("permanent", 6),
        ),
    ),
    # Autonomous
    Question(
        "autonomous",
        "{name}",
        "choice",
        default="no",
        instructions="Does this object move and act on its own?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    # Gated on autonomous=true
    Question(
        "speed",
        "{name}",
        "choice",
        default="normal",
        gates=(GATE_AUTONOMOUS,),
        instructions="Rate this creature's movement speed.",
        choices=("crawl", "slow", "normal", "fast", "rapid"),
        choice_map=(("crawl", 0), ("slow", 1), ("normal", 2), ("fast", 3), ("rapid", 4)),
    ),
    Question(
        "affordance",
        "{name}",
        "choice",
        default="none",
        instructions=(
            "In a 2D game, how can a player interact with this object? "
            "carry=pick up and hold, ride=sit on top and move, "
            "scale=climb up it, none=cannot interact physically."
        ),
        choices=("carry", "ride", "scale", "none"),
        choice_map=(("carry", 0), ("ride", 1), ("scale", 2), ("none", 3)),
    ),
    # ---- State properties (initial + susceptible) ----
    # Initial states — does this object spawn with these states?
    Question(
        "initially_burning",
        "{name}",
        "choice",
        default="no",
        instructions="Does this object produce fire or heat?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_frozen",
        "{name}",
        "choice",
        default="no",
        instructions="Is this object frozen or ice-cold?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_wet",
        "{name}",
        "choice",
        default="no",
        instructions="Is this object wet or made of water or liquid?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "initially_electrified",
        "{name}",
        "choice",
        default="no",
        instructions="Does this object produce electricity?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    # Susceptible states — can these states spread to this object?
    Question(
        "catches_fire",
        "{name}",
        "choice",
        default="no",
        instructions="Can this object catch fire from a nearby burning object?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "can_freeze",
        "{name}",
        "choice",
        default="no",
        instructions="Can this object freeze from contact with something frozen?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "gets_wet",
        "{name}",
        "choice",
        default="no",
        instructions="Can this object get wet from a nearby wet object?",
        choices=("yes", "no"),
        choice_map=(("yes", 1), ("no", 0)),
    ),
    Question(
        "conducts_electricity",
        "{name}",
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
    "Give a 1-5 word game object name for: {description}. Reply with ONLY the name, nothing else.",
    "text",
    max_tokens=20,
    default="Object",
)

VISUAL_QUESTION = Question(
    "visual_description",
    "Describe the appearance of '{name}' for a 2D sprite artist. "
    "Shape, material, colors, distinctive features. "
    "Max 2 sentences. Reply with ONLY the description.",
    "text",
    max_tokens=40,
    default="a {name}",
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
