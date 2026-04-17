"""Data-driven question definitions for the object creation pipeline.

Every LLM call that runs during object creation is defined here as a
`Question` instance. Edit this file to add, remove, or tweak object
properties during playtesting. Gate conditions control conditional fan-out
(e.g. `speed` only fires when `active=true`).

Consumed by `app.creator.pipeline.create_object` via `run_questions()`.
"""

from __future__ import annotations

from app.creator.question_graph import Gate, Question

# ---- Reusable gate conditions ----

GATE_ACTIVE = Gate("active", lambda v: bool(v))
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
            "Use the OVERALL size including any rotors, wings, masts, tails, or extensions — "
            "not just the main body or cabin. "
            "Examples: coin=2, apple=8, cat=25, chair=90, person=175, "
            "drone=40, helicopter=400 (body + rotor), airplane=500 (tail), "
            "tree=800, sailing ship=2000 (mast), mountain=5000. "
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
        "choice",
        default="falls",
        instructions=(
            "How does this object behave vertically during normal operation? "
            "rises = actively moves upward (helium balloon, smoke, hot ember). "
            "hovers = maintains altitude under its own power "
            "(helicopter, drone, bird, hot air balloon, flying monster). "
            "drifts = slow fall due to air resistance (feather, leaf, snowflake, dust mote). "
            "falls = falls normally, the default "
            "(person, ball, anvil, book, car, boulder, everything else). "
            "For powered aircraft and flying creatures, pick the active flying state, "
            "not what would happen if the engine stopped."
        ),
        choices=("rises", "hovers", "drifts", "falls"),
        # Ints are chosen so GravityToScale in PhysicsApplicator.cs yields the
        # desired Godot GravityScale: rises=-1.0, hovers=0.0, drifts~0.5, falls~1.1.
        # If that piecewise map changes, recompute these.
        choice_map=(("rises", 0), ("hovers", 25), ("drifts", 38), ("falls", 55)),
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
    # Active
    Question(
        "active",
        "{description}",
        "choice",
        default="passive",
        instructions=(
            "Does this object do something during gameplay, or is it inert physics? "
            "Active: animals, creatures, monsters, robots, people, vehicles, aircraft, "
            "and any machine, device, or substance that moves or reacts on its own "
            "(a bomb explodes on contact, a fan blows air, acid corrodes). "
            "Passive: plants, hand tools, furniture, terrain, food, and inert props."
        ),
        choices=("active", "passive"),
        choice_map=(("active", 1), ("passive", 0)),
    ),
    # Gated on active=true
    Question(
        "speed",
        "{description}",
        "choice",
        default="normal",
        gates=(GATE_ACTIVE,),
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
    # Initial state — what elemental state, if any, does this object spawn as?
    # Single-pick: an object's elemental identity is one axis. The susceptibility
    # questions below cover the orthogonal "what can be applied to it" axis.
    Question(
        "initial_state",
        "{description}",
        "choice",
        default="none",
        instructions=(
            "When this object spawns into the world, is it actively a source of any "
            "elemental state? "
            "burning=produces fire/heat (torch, lava, flame); "
            "frozen=is solid ice or radiates cold (ice block, frost crystal); "
            "wet=is liquid water or actively dripping (water, puddle, soaked sponge); "
            "electrified=is actively conducting/emitting electricity (live wire, lightning); "
            "none=an ordinary inert object (rock, wood, metal box)."
        ),
        choices=("none", "burning", "frozen", "wet", "electrified"),
        choice_map=(("none", 0), ("burning", 1), ("frozen", 2), ("wet", 3), ("electrified", 4)),
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

# ---- Text questions — also Question instances with gates ----

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
