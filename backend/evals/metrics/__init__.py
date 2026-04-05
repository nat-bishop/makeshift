"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from app.engine.rules_data import ALL_RULES
from pydantic_ai.settings import ModelSettings
from pydantic_evals.evaluators import LLMJudge

from evals.metrics.element_accuracy import ElementAccuracyEvaluator
from evals.metrics.interaction_surface import InteractionSurfaceEvaluator
from evals.metrics.living_movement import HasSignatureEvaluator
from evals.metrics.rubric_context import get_rules_summary_string, get_tag_list_string
from evals.metrics.substance_accuracy import SubstanceAccuracyEvaluator
from evals.metrics.tag_recall import TagRecallEvaluator
from evals.metrics.validity import ValidityEvaluator

_TAG_LIST = get_tag_list_string()
_RULES_SUMMARY = get_rules_summary_string()

RUBRICS: dict[str, str] = {
    "Faithfulness": (
        "You are evaluating a V2 game object design for a 2D physics sandbox game "
        "(like Scribblenauts). A player typed a description, and an AI designed a "
        "game object with a substance, optional element, tags, behaviors, and visual.\n\n"
        "Evaluate whether the design faithfully represents what the player asked for.\n\n"
        "Score on this scale:\n"
        "- 1.0: Substance matches material, element matches energy type, tags are correct. "
        "Name matches the concept.\n"
        "- 0.75: Core concept captured. ONE minor issue (slightly off substance/element, "
        "missing a secondary tag).\n"
        "- 0.50: Wrong substance or element that contradicts the concept, OR missing "
        "a key tag.\n"
        "- 0.25: Multiple core choices wrong. Could describe a different object.\n"
        "- 0.0: No meaningful connection to the player's description.\n\n"
        f"VALID TAGS (0-3 per object):\n{_TAG_LIST}\n\n"
        "Substances: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, "
        "slime, ice, lava, fire, smoke, flesh\n"
        "Elements: burning, electric, magnetic, freezing, acidic, toxic, windy\n"
    ),
    "Gameplay Quality": (
        "You are evaluating a V2 game object design for a 2D physics sandbox where "
        "substance determines physics and the tag system drives interactions.\n\n"
        f"VALID TAGS (0-3 per object):\n{_TAG_LIST}\n\n"
        f"COMPLETE TAG INTERACTION RULES ({len(ALL_RULES)} rules — "
        "these fire automatically):\n"
        f"{_RULES_SUMMARY}\n\n"
        "V2 DESIGN: Substance provides physics (mass, durability, friction). Element "
        "adds energy traits. Tags add independent modifiers. Behaviors define creature "
        "personality via verb+target (destroy, eat, investigate, follow, protect, flee).\n\n"
        "Score on this scale:\n"
        "- 1.0: Substance + element + tags create rich interaction surfaces. Behaviors "
        "(if present) add meaningful personality.\n"
        "- 0.75: Strong choices with ONE missed opportunity.\n"
        "- 0.50: Substance or element doesn't match the concept, OR tags create no "
        "meaningful interactions.\n"
        "- 0.25: Multiple poor choices. Object is inert or contradictory.\n"
        "- 0.0: No useful gameplay properties.\n"
    ),
    "Sprite Prompt": (
        "You are evaluating a visual description that will be used to generate a 2D "
        "game sprite image.\n\n"
        "Score on this scale:\n"
        "- 1.0: Clear shape, materials, colors, distinctive features. Recognizable sprite.\n"
        "- 0.75: Good with minor gaps.\n"
        "- 0.5: Vague or contradictory.\n"
        "- 0.25: Very vague, describes a scene, or contradicts the object.\n"
        "- 0.0: Empty, nonsensical, or unrelated.\n\n"
        f"VALID TAGS:\n{_TAG_LIST}\n"
        "Verify the visual description is consistent with the substance and tags."
    ),
}

METRIC_NAMES: list[str] = [
    "Validity", "Substance Accuracy", "Element Accuracy", "Tag Recall",
    "Interaction Surface", "Has Signature", *RUBRICS.keys(),
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


def default_evaluators() -> list:
    """Build the standard set of evaluators for creator agent evals."""
    return [
        ValidityEvaluator(),
        SubstanceAccuracyEvaluator(),
        ElementAccuracyEvaluator(),
        TagRecallEvaluator(),
        InteractionSurfaceEvaluator(),
        HasSignatureEvaluator(),
        *(make_judge(name) for name in RUBRICS),
    ]
