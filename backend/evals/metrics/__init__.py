"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from app.engine.rules_data import ALL_RULES
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
        "- 1.0: The design captures the core concept perfectly. Tags, behaviors, and "
        "visuals all reinforce the player's intent. No irrelevant or contradictory elements.\n"
        "- 0.75: The design captures the main idea with minor issues — one slightly off "
        "tag, a missing but non-critical behavior, or a small visual mismatch.\n"
        "- 0.5: The design partially captures the concept but has notable gaps — missing "
        "a key tag that defines the object, or includes behaviors/tags that don't fit "
        "the description.\n"
        "- 0.25: The design misses the core concept — wrong physical properties, "
        "contradictory theme, or behaviors that work against the player's intent.\n"
        "- 0.0: The design bears no meaningful relationship to the player's description.\n\n"
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
        f"VALID TAGS (1-4 per object):\n{_TAG_LIST}\n\n"
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
        "- 1.0: Excellent design that exploits the tag system for emergent gameplay. "
        "Tags chosen create interesting interaction surfaces with other objects. "
        "Signature behavior (if present) complements tags rather than duplicating "
        "what tags already do. Examples of 1.0 designs:\n"
        "  * A napalm monster with HEAT_SOURCE + STICKY — fire spreads AND things "
        "stick to it, plus ADD_TAGS(FLAMMABLE) signature to make nearby objects "
        "catchable by fire\n"
        "  * A simple rock with HEAVY + RIGID — no signature needed, tags "
        "fully define it\n"
        "  * A wind spirit with LIVING + WIND_SOURCE + FLOATING — tags create "
        "continuous push forces, LIVING implies wander movement\n"
        "- 0.75: Good design with minor missed opportunities. Core tags are right but "
        "one interaction opportunity missed (e.g., a wooden object without FLAMMABLE, "
        "or a creature with only HOSTILE instead of using richer tag interactions).\n"
        "- 0.5: Mediocre design. Falls into the 'generic damage' trap — uses only "
        "HOSTILE when tags like HEAT_SOURCE, SHARP, ACIDIC, or "
        "TOXIC would create richer interactions automatically. Or has tags that don't "
        "create any meaningful interaction surfaces.\n"
        "- 0.25: Poor design. Tags and signature work against each other, or the "
        "object is inert when it should be interactive. Wasted budget on tags that "
        "don't interact with anything.\n"
        "- 0.0: No useful gameplay properties. Wrong tags, no interaction surfaces, "
        "completely generic.\n\n"
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


def make_judge(name: str) -> LLMJudge:
    """Create an LLM-as-judge evaluator for the given metric."""
    return LLMJudge(
        rubric=RUBRICS[name],
        include_input=True,
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
