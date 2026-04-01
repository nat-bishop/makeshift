"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from app.engine.rules_data import ALL_RULES
from pydantic_ai.settings import ModelSettings
from pydantic_evals.evaluators import LLMJudge

from evals.metrics.interaction_surface import InteractionSurfaceEvaluator
from evals.metrics.living_movement import HasSignatureEvaluator
from evals.metrics.rubric_context import get_rules_summary_string, get_tag_list_string
from evals.metrics.tag_recall import TagRecallEvaluator
from evals.metrics.validity import ValidityEvaluator

_TAG_LIST = get_tag_list_string()
_RULES_SUMMARY = get_rules_summary_string()

RUBRICS: dict[str, str] = {
    "Faithfulness": (
        "You are evaluating a game object design for a 2D physics sandbox game "
        "(like Scribblenauts). A player typed a description, and an AI designed a "
        "game object with a name, tags, behaviors, and visual description.\n\n"
        "Evaluate whether the design faithfully represents what the player asked for.\n\n"
        "Score on this scale:\n"
        "- 1.0: Every tag directly supports the player's description. Name matches the "
        "concept. No irrelevant or contradictory tags.\n"
        "- 0.75: Core concept is captured. ONE of: slightly off tag choice, target "
        "auto-inference imprecision (NEAREST_LIVING vs NEAREST_PLAYER), or a missing "
        "secondary attribute.\n"
        "- 0.50: Missing a tag that defines the core concept (e.g., no FLYING for"
        "something that flies), OR includes a tag that contradicts the description.\n"
        "- 0.25: Multiple core tags are wrong or missing. The design could describe a "
        "different object entirely.\n"
        "- 0.0: No meaningful connection to the player's description.\n\n"
        "SCORED EXAMPLES (use these to calibrate your scoring):\n\n"
        'Example 1 — Score 1.0:\n'
        'Input: "fire sword"\n'
        'Output: name "Fire Sword", tags [RIGID, SHARP, HEAT_SOURCE, FLAMMABLE]\n'
        "Why 1.0: Name matches. SHARP captures 'sword', HEAT_SOURCE captures 'fire'. "
        "All tags reinforce the concept.\n\n"
        'Example 2 — Score 0.75:\n'
        'Input: "healing mushroom that heals you when you kick it"\n'
        'Output: name "Healing Cap", tags [LIVING, BREAKABLE], '
        'signature "ON_DAMAGED -> HEAL -> NEAREST_LIVING"\n'
        "Why 0.75: Core concept captured (mushroom that heals on kick). Minor issue: "
        "NEAREST_LIVING instead of NEAREST_PLAYER means it heals any creature, not "
        "specifically the player.\n\n"
        'Example 3 — Score 0.25:\n'
        'Input: "a parachute that slows you down when falling"\n'
        'Output: name "War Chute", tags [HEAVY, RIGID, SHARP], '
        'signature "ON_PROXIMITY -> DAMAGE"\n'
        "Why 0.25: A parachute should be LIGHT and FLYING, not HEAVY and SHARP. "
        "The combat signature contradicts the slow-fall concept entirely.\n\n"
        "Focus on: Does the name match the concept? Do the tags reflect the object's "
        "core physical nature? Do the behaviors match what the player described or "
        "implied? Does the visual description match the tags and name?\n\n"
        f"VALID TAGS (only these exist — no others):\n{_TAG_LIST}\n\n"
        "Do NOT penalize the design for missing tags that don't exist in this list "
        "(e.g., there is no EDIBLE, FOOD, WOODEN, or METAL tag)."
    ),
    "Gameplay Quality": (
        "You are evaluating a game object design for a 2D physics sandbox where objects "
        "interact through a TAG SYSTEM. Tags create automatic interactions — this is "
        "the core of the game's emergent gameplay.\n\n"
        f"VALID TAGS (2-5 per object):\n{_TAG_LIST}\n\n"
        f"COMPLETE TAG INTERACTION RULES ({len(ALL_RULES)} rules — "
        "these fire automatically, no behaviors needed):\n"
        f"{_RULES_SUMMARY}\n\n"
        "TAG-IMPLIED BEHAVIORS (automatic from tags, not authored by the designer):\n"
        "- HOSTILE + LIVING → chases nearest creature, flees when hurt\n"
        "- LIVING (alone) → wanders passively\n"
        "- EXPLOSIVE → detonates when damaged\n\n"
        "SIGNATURE BEHAVIOR (optional, at most 1 per object):\n"
        "A single unique behavior that makes this specific object unusual — "
        "ranged attacks, healing, tag mutation, or reactive transformations. "
        "Most objects don't need one. Tags + implied behaviors handle the rest.\n"
        "- ADD_TAGS is especially powerful — it can spread tags to other objects, "
        "creating chain reactions\n\n"
        "Evaluate the GAMEPLAY QUALITY of this design — does it create interesting "
        "interactions?\n\n"
        "Score on this scale:\n"
        "- 1.0: Tags create multiple interaction surfaces with other objects. Signature "
        "(if present) adds a capability tags can't provide. No wasted or contradictory tags.\n"
        "- 0.75: Strong tag choices with ONE missed opportunity — a natural tag omission "
        "(e.g., wooden object missing FLAMMABLE) or a signature that partially overlaps "
        "with tag behavior.\n"
        "- 0.50: Tags include a contradiction that undermines the design intent (check "
        "the rules — does a tag enable damage the object should resist?), OR tags "
        "create no meaningful interaction surfaces despite having room for more.\n"
        "- 0.25: Multiple tags contradict each other or the design intent. Signature "
        "duplicates what tags already do. Object is inert when it should be interactive.\n"
        "- 0.0: No useful gameplay properties. Tags create zero interaction surfaces.\n\n"
        "KEY PRINCIPLE: Tags are the primary gameplay driver. A fire sword "
        "with HEAT_SOURCE will ignite FLAMMABLE objects without needing a signature. "
        "Tags like SHARP, HOSTILE, HEAT_SOURCE, TOXIC, and ACIDIC all deal "
        "contact damage automatically. LIVING creatures get movement automatically. "
        "The signature is only for ONE unique action tags can't provide "
        "(ranged attacks, healing, tag spreading, reactive transformations).\n\n"
        "Simple objects with well-chosen tags CAN score 1.0. A rock doesn't need "
        "a signature. But a fire-breathing dragon with only HOSTILE instead "
        "of using HEAT_SOURCE + SPAWN_PROJECTILE signature should score lower."
    ),
    "Sprite Prompt": (
        "You are evaluating a visual description that will be used to generate a 2D "
        "game sprite image. The description should produce a clear, recognizable sprite "
        "when fed to an image generation model.\n\n"
        "Score on this scale:\n"
        "- 1.0: Description clearly specifies shape, materials, colors, and distinctive "
        "features. Would produce a recognizable, distinctive sprite. Matches the "
        "object's name and tags.\n"
        "- 0.75: Good description with minor gaps — missing a color, slightly generic, "
        "but would still produce a reasonable sprite.\n"
        "- 0.5: Vague or partially contradictory. Would produce a generic or confusing "
        "sprite. Missing key visual features implied by the tags.\n"
        "- 0.25: Very vague, describes a scene instead of an object, or contradicts "
        "the tags significantly.\n"
        "- 0.0: Empty, nonsensical, or completely unrelated to the object.\n\n"
        "The description should describe the object itself (shape, material, color), "
        "not a scene or environment. It should be 1-2 sentences.\n\n"
        f"VALID TAGS:\n{_TAG_LIST}\n"
        "Verify the visual description is consistent with the assigned tags."
    ),
}

METRIC_NAMES: list[str] = [
    "Validity", "Tag Recall", "Interaction Surface", "Has Signature", *RUBRICS.keys()
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
        TagRecallEvaluator(),
        InteractionSurfaceEvaluator(),
        HasSignatureEvaluator(),
        *(make_judge(name) for name in RUBRICS),
    ]
