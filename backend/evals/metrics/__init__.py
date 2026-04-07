"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from pydantic_ai.settings import ModelSettings
from pydantic_evals.evaluators import LLMJudge

from evals.metrics.category_accuracy import CategoryAccuracyEvaluator
from evals.metrics.element_accuracy import ElementAccuracyEvaluator
from evals.metrics.has_signature import HasSignatureEvaluator
from evals.metrics.interaction_surface import InteractionSurfaceEvaluator
from evals.metrics.rubric_context import get_tag_list_string
from evals.metrics.substance_accuracy import SubstanceAccuracyEvaluator
from evals.metrics.tag_recall import TagRecallEvaluator
from evals.metrics.validity import ValidityEvaluator

_TAG_LIST = get_tag_list_string()

# --- Rubric design notes ---
# All LLM judge metrics use a 3-point anchored scale (0.0 / 0.5 / 1.0) with concrete
# game-specific examples at each level. This avoids the 0.75-compression problem where
# 5-point scales with generic descriptions cause judges to default to "mostly fine."
# Anchors use real game objects and tag interactions so the judge has clear boundaries.

RUBRICS: dict[str, str] = {
    # Faithfulness: does the design match the player's intent?
    # Scored on literal fidelity, not creativity. A "fire sword" that's metal+burning+SHARP
    # is 1.0 even if boring. Creative liberties are fine as long as they don't contradict.
    "Faithfulness": (
        "You are evaluating a game object design for a 2D physics sandbox (like Scribblenauts). "
        "A player typed a description, and an AI designed a game object with a substance, "
        "optional element, tags, behaviors, and visual description.\n\n"
        "**Question: Does this design faithfully represent what the player typed?**\n\n"
        "Score EXACTLY one of 0.0, 0.5, or 1.0:\n\n"
        "- **0.0 — Fail:** No meaningful connection to the player's description. "
        "Example: player typed 'fire sword' but got substance=water, no burning element, "
        "no SHARP tag — nothing says 'fire' or 'sword.'\n\n"
        "- **0.5 — Partial:** Core concept is present but one significant mismatch. "
        "Example: 'wooden sword' gets substance=stone instead of wood. Or 'fire sword' has "
        "metal+SHARP but is missing the burning element entirely.\n\n"
        "- **1.0 — Pass:** Substance matches the material, element matches the energy type, "
        "tags fit the concept. Creative liberties are fine — 'ice cream' mapped to "
        "substance=slime is acceptable if the rest is coherent. Example: 'fire sword' → "
        "metal + burning + SHARP.\n\n"
        f"VALID TAGS (0-3 per object):\n{_TAG_LIST}\n\n"
        "Substances: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, "
        "slime, ice, lava, fire, smoke, flesh\n"
        "Elements: burning, electric, magnetic, freezing, acidic, toxic, windy\n"
    ),
    # Delight: proxy for player reaction, not system correctness.
    # A player doesn't know the 56 rules — they just want something that feels right and
    # makes them want to experiment. No rules context is provided to the judge on purpose.
    "Delight": (
        "You are evaluating a game object design for a 2D physics sandbox (like Scribblenauts). "
        "A player typed a description, and an AI designed a game object.\n\n"
        "**Question: If you were a player who typed this, would you be delighted by the "
        "result? Would you want to experiment with it and see what happens when you combine "
        "it with other objects?**\n\n"
        "Score EXACTLY one of 0.0, 0.5, or 1.0:\n\n"
        "- **0.0 — Fail:** Boring or broken. The object contradicts the player's fantasy or "
        "has no interesting properties. Example: player typed 'explosive barrel' but got "
        "substance=stone with no EXPLOSIVE tag — it's just a rock shaped like a barrel.\n\n"
        "- **0.5 — Partial:** Competent but obvious. The substance and element are correct "
        "but the design doesn't invite experimentation. Example: 'rock' → stone with no "
        "tags, no element — technically correct but it's just an inert lump. Or 'fire sword' "
        "→ metal + burning + SHARP with zero behaviors — functional but predictable.\n\n"
        "- **1.0 — Pass:** Surprising-but-fitting. The design includes choices that invite "
        "experimentation beyond what the player explicitly asked for. Example: 'rock' → "
        "stone + BREAKABLE (now it shatters when hit!). Or 'campfire' → fire substance + "
        "STICKY (things get caught in the flames). Creative liberties that make you think "
        "'oh cool, I wonder what happens if...' are exactly what earns a 1.0.\n\n"
        "Substances: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, "
        "slime, ice, lava, fire, smoke, flesh\n"
        "Elements: burning, electric, magnetic, freezing, acidic, toxic, windy\n"
    ),
    # Visual Clarity: can an image model produce a recognizable sprite from this description?
    # Penalizes scene descriptions and vagueness. Rewards specificity about shape, material,
    # and color — the things that make a good 2D game sprite.
    "Visual Clarity": (
        "You are evaluating a visual description that will be sent to an image generation "
        "model to produce a 2D game sprite.\n\n"
        "**Question: Could an image model generate a recognizable, distinctive game sprite "
        "from this visual description?**\n\n"
        "Score EXACTLY one of 0.0, 0.5, or 1.0:\n\n"
        "- **0.0 — Fail:** Empty, nonsensical, describes a scene instead of an object, or "
        "contradicts the substance/tags. Example: the description says 'a vast mountain "
        "landscape with rolling clouds' for what should be a single sword sprite.\n\n"
        "- **0.5 — Partial:** Recognizable but generic — could describe many different "
        "objects. Missing distinctive features, colors, or material cues. Example: 'a round "
        "thing' for a health potion, or 'a creature' for an acid spider.\n\n"
        "- **1.0 — Pass:** Clear shape, material texture, colors, and distinctive features "
        "that match the substance and tags. Example: 'a translucent glass sphere filled with "
        "swirling green liquid, faintly glowing, sealed with a small cork' for a health "
        "potion. The description doesn't need to be long — just specific enough to produce "
        "a recognizable sprite.\n\n"
        f"VALID TAGS:\n{_TAG_LIST}\n"
        "Verify the visual description is consistent with the substance and tags."
    ),
}

METRIC_NAMES: list[str] = [
    "Validity", "Substance Accuracy", "Element Accuracy", "Category Accuracy",
    "Tag Recall", "Interaction Surface", "Has Signature", *RUBRICS.keys(),
]


JUDGE_SETTINGS = ModelSettings(temperature=0.0)


def make_judge(name: str) -> LLMJudge:
    """Create an LLM-as-judge evaluator for the given metric."""
    return LLMJudge(
        rubric=RUBRICS[name],
        include_input=True,
        model_settings=JUDGE_SETTINGS,
        score={"evaluation_name": name, "include_reason": True},
        assertion=False,
    )


def _deterministic_evaluators() -> list:
    return [
        ValidityEvaluator(),
        SubstanceAccuracyEvaluator(),
        ElementAccuracyEvaluator(),
        CategoryAccuracyEvaluator(),
        TagRecallEvaluator(),
        InteractionSurfaceEvaluator(),
        HasSignatureEvaluator(),
    ]


def default_evaluators() -> list:
    """Build the standard set of evaluators for creator agent evals."""
    return [*_deterministic_evaluators(), *(make_judge(name) for name in RUBRICS)]


def gate_evaluators() -> list:
    """Deterministic-only evaluators for fast gate checks. No LLM judge calls."""
    return _deterministic_evaluators()
