import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class Question:
    key: str
    prompt_template: str  # {name} substituted at call time
    max_tokens: int
    parse: Callable[[str], int | float | bool | str]


def parse_int(s: str) -> int:
    m = re.search(r"\d+", s.strip())
    return int(m.group()) if m else 0


def parse_float(s: str) -> float:
    m = re.search(r"[\d.]+", s.strip())
    return float(m.group()) if m else 1.0


def parse_bool(s: str) -> bool:
    return s.strip().startswith("1")


def parse_text(s: str) -> str:
    return s.strip()


CREATION_QUESTIONS: list[Question] = [
    Question(
        "mass_kg",
        "How heavy is {name} in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70,"
        " car=1500, house=50000). Reply with just the number.",
        4,
        parse_float,
    ),
    Question(
        "height_cm",
        "How tall/long is {name} in cm? (ant=1, mouse=5, coin=2, sword=120, human=170,"
        " horse=200, house=800). Reply with just the number.",
        2,
        parse_int,
    ),
    Question(
        "friction",
        "How grippy is {name} 0-100? (ice=0, metal=30, wood=50, rubber=90)."
        " Reply with just the number.",
        1,
        parse_int,
    ),
    Question(
        "bounce",
        "How bouncy is {name} 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)."
        " Reply with just the number.",
        1,
        parse_int,
    ),
    Question(
        "gravity",
        "Gravity pull on {name} 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50,"
        " rock=60, anvil=75). Reply with just the number.",
        1,
        parse_int,
    ),
    Question(
        "armor",
        "How resistant to damage is {name} 0-100? (paper=5, wood=30, steel=80, diamond=99)."
        " Reply with just the number.",
        1,
        parse_int,
    ),
    Question(
        "hp",
        "How much punishment can {name} take before destroyed 0-100? (balloon=5, wood=40,"
        " steel=80). Reply 0 if indestructible. Reply with just the number.",
        1,
        parse_int,
    ),
    Question(
        "indestructible",
        "Can {name} be destroyed? 0=yes it can be destroyed, 1=no it is indestructible."
        " Reply with just 0 or 1.",
        1,
        parse_bool,
    ),
    Question(
        "has_field",
        "Does {name} affect nearby things without touching them (heat, magnetism, wind,"
        " radiation)? 0=no 1=yes. Reply with just 0 or 1.",
        1,
        parse_bool,
    ),
    Question(
        "field_range_cm",
        "If {name} affects nearby things, what range in cm? (candle=50, campfire=250,"
        " bonfire=500, volcano=1000). Reply 0 if no field. Reply with just the number.",
        2,
        parse_int,
    ),
    Question(
        "autonomous",
        "Is {name} a living creature that moves on its own? 0=no 1=yes."
        " Reply with just 0 or 1.",
        1,
        parse_bool,
    ),
    Question(
        "affordance",
        "When a player interacts with {name}: 0=carry it, 1=ride/mount it, 2=climb it,"
        " 3=nothing/no interaction. Reply with just the number.",
        1,
        parse_int,
    ),
]

VISUAL_QUESTION = Question(
    "visual_description",
    "Describe {name} for a 2D game sprite artist in 1-2 sentences. Focus on shape, material,"
    " colors, distinctive features. Describe only the object, not a scene.",
    60,
    parse_text,
)

DESTRUCTION_QUESTION = Question(
    "destruction_result_name",
    "When {name} is destroyed, what remains? Reply with a 1-3 word name for the debris"
    " (e.g. 'broken glass shards', 'pile of splinters', 'metal scraps')."
    " If nothing remains, reply 'nothing'.",
    8,
    parse_text,
)
