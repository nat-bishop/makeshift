"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from pydantic_evals.evaluators import LLMJudge

from evals.metrics.validity import ValidityEvaluator

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
        "implied? Does the visual description match the tags and name?"
    ),
    "Gameplay Quality": (
        "You are evaluating a game object design for a 2D physics sandbox where objects "
        "interact through a TAG SYSTEM. Tags create automatic interactions — this is "
        "the core of the game's emergent gameplay. Here are the key tag interactions:\n\n"
        "TAG INTERACTIONS (automatic, no behaviors needed):\n"
        "- HEAT_SOURCE ignites FLAMMABLE objects on contact (fire spreads!)\n"
        "- ELECTRIC propagates through CONDUCTING objects (chain lightning!)\n"
        "- WIND_SOURCE pushes LIGHT objects continuously at range\n"
        "- MAGNETIC attracts CONDUCTING objects at range\n"
        "- CORROSIVE dissolves materials on contact\n"
        "- FROZEN makes surfaces slippery; COLD freezes LIQUID on contact\n"
        "- SHARP deals cut damage on contact\n"
        "- STICKY creates physical joints on contact (things stick together!)\n"
        "- EXPLOSIVE detonates from heat or electricity for massive area damage\n"
        "- REFLECTIVE bounces back heat and electricity\n\n"
        "BEHAVIORS (0-3 per object) make objects autonomous:\n"
        "- Movement: MOVE_TOWARD, MOVE_AWAY, PATROL\n"
        "- Combat: DEAL_DAMAGE, SPAWN_PROJECTILE, EXPLODE, APPLY_FORCE\n"
        "- Utility: HEAL, ADD_TAGS, REMOVE_TAGS, ATTRACT\n"
        "- ADD_TAGS is especially powerful — it can spread tags to other objects, "
        "creating chain reactions\n\n"
        "Evaluate the GAMEPLAY QUALITY of this design — does it create interesting "
        "interactions?\n\n"
        "Score on this scale:\n"
        "- 1.0: Excellent design that exploits the tag system for emergent gameplay. "
        "Tags chosen create interesting interaction surfaces with other objects. "
        "Behaviors (if present) complement tags rather than duplicating what tags "
        "already do. Examples of 1.0 designs:\n"
        "  * A napalm monster with HEAT_SOURCE + STICKY — fire spreads AND things "
        "stick to it, plus ADD_TAGS(FLAMMABLE) behavior to make nearby objects "
        "catchable by fire\n"
        "  * A simple rock with SOLID + HEAVY + RIGID — no behaviors needed, tags "
        "fully define it\n"
        "  * A wind spirit with LIVING + WIND_SOURCE + FLOATING — tags create "
        "continuous push forces, MOVE_TOWARD behavior makes it chase\n"
        "- 0.75: Good design with minor missed opportunities. Core tags are right but "
        "one interaction opportunity missed (e.g., a wooden object without FLAMMABLE, "
        "or a creature with only DEAL_DAMAGE instead of using tag interactions).\n"
        "- 0.5: Mediocre design. Falls into the 'just deal damage' trap — uses "
        "ON_CONTACT -> DEAL_DAMAGE when tags like HEAT_SOURCE, SHARP, CORROSIVE, or "
        "TOXIC would create richer interactions automatically. Or has tags that don't "
        "create any meaningful interaction surfaces.\n"
        "- 0.25: Poor design. Tags and behaviors work against each other, or the "
        "object is inert when it should be interactive. Wasted budget on tags that "
        "don't interact with anything.\n"
        "- 0.0: No useful gameplay properties. Wrong tags, no interaction surfaces, "
        "completely generic.\n\n"
        "KEY PRINCIPLE: The tag system handles interactions automatically. A fire sword "
        "with HEAT_SOURCE will ignite FLAMMABLE objects without needing a behavior for "
        "it. Designs that use behaviors to duplicate what tags already provide (e.g., "
        "ON_CONTACT -> DEAL_DAMAGE on a SHARP object) are wasting behavior budget. "
        "The best designs use tags for passive interactions and behaviors for things "
        "tags CAN'T do (movement, timed actions, conditional reactions, tag spreading).\n\n"
        "Simple objects with well-chosen tags CAN score 1.0. A rock doesn't need "
        "behaviors. But a fire-breathing dragon that only does DEAL_DAMAGE instead "
        "of using HEAT_SOURCE + SPAWN_PROJECTILE should score lower."
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
        "not a scene or environment. It should be 1-2 sentences."
    ),
}

METRIC_NAMES: list[str] = ["Validity", *RUBRICS.keys()]


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
        *(make_judge(name) for name in RUBRICS),
    ]
