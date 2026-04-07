"""Data-driven question lists for V3 creator pipeline.

Each question is a single LLM call producing 1-4 tokens.
Edit this file to add, remove, or tweak object properties during playtesting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    key: str
    prompt: str  # f-string with {name} placeholder
    qtype: str  # "int", "float", "bool"
    lo: int | float = 0
    hi: int | float = 100
    default: int | float = 50


# All fired in parallel via asyncio.gather (~200ms wall time)
CREATION_QUESTIONS: list[Question] = [
    # Physics (5 questions)
    Question(
        "mass_kg",
        "How heavy is {name} in kg? "
        "(ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500)",
        "float", 0.001, 100000, 1.0,
    ),
    Question(
        "height_cm",
        "How tall is {name} in cm? "
        "(ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800)",
        "int", 1, 5000, 30,
    ),
    Question(
        "friction",
        "How grippy is {name} 0-100? (ice=0, metal=30, wood=50, rubber=90)",
        "int",
    ),
    Question(
        "bounce",
        "How bouncy is {name} 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)",
        "int", 0, 100, 10,
    ),
    Question(
        "gravity",
        "Gravity pull on {name} 0-100? "
        "(balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75)",
        "int",
    ),
    # Destructibility (3 questions)
    Question(
        "armor",
        "How resistant to damage is {name} 0-100? (paper=5, wood=30, steel=80, diamond=99)",
        "int", 0, 100, 30,
    ),
    Question(
        "hp",
        "How much punishment before {name} is destroyed 0-100? "
        "(balloon=5, wood=40, steel=80)",
        "int", 0, 100, 50,
    ),
    Question(
        "indestructible",
        "Can {name} be destroyed? 0=yes 1=no (mountain=1, sword=0)",
        "bool",
    ),
    # Classification (3 questions)
    Question(
        "has_field",
        "Does {name} affect nearby things without touching "
        "(heat, cold, magnetism, toxin)? 0=no 1=yes",
        "bool",
    ),
    Question(
        "field_range_cm",
        "If {name} has area effect, range in cm? "
        "(candle=50, campfire=250, bonfire=500, volcano=1000)",
        "int", 10, 1000, 100,
    ),
    Question(
        "autonomous",
        "Is {name} a living creature or autonomous being? 0=no 1=yes",
        "bool",
    ),
    # Affordance (1 question — single choice, 1 token)
    Question(
        "affordance",
        "When a player interacts with {name}: "
        "0=carry it 1=ride it 2=climb it 3=nothing",
        "int", 0, 3, 3,
    ),
]

NAME_PROMPT = (
    "Give a 1-3 word game object name for: {description}. "
    "Reply with ONLY the name, nothing else."
)

VISUAL_PROMPT = (
    "Describe the appearance of '{name}' ({description}) for a 2D sprite artist. "
    "Shape, material, colors, distinctive features. "
    "Max 2 sentences. Reply with ONLY the description."
)
