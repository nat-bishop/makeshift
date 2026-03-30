"""Eval metrics for the creator agent.

Provides deterministic validity checks and LLM-as-judge scoring.
"""

from __future__ import annotations

from pydantic_evals.evaluators import LLMJudge

from evals.metrics.validity import ValidityEvaluator

RUBRICS: dict[str, str] = {
    "Relevance": (
        "Evaluate whether the game object's tags and behaviors are relevant to "
        "the player's description. Tags should reflect the core physical and "
        "thematic properties of the described object. Behaviors should match what "
        "the object would naturally do. For example, a 'fire sword' should have "
        "heat/fire-related tags and combat behaviors. A 'healing fountain' should "
        "have liquid tags and healing behaviors. Penalize objects that ignore the "
        "core concept of the description or add irrelevant tags."
    ),
    "Creativity": (
        "Evaluate whether this game object design is creative and interesting "
        "for a 2D sandbox game. Good designs have: surprising but fitting tag "
        "combinations that create emergent gameplay, behaviors that make the "
        "object feel alive or interactive, and evocative names. Bad designs are "
        "generic (e.g., just SOLID+RIGID with no behaviors) or miss obvious "
        "gameplay opportunities (e.g., a fire sword with no HEAT_SOURCE tag). "
        "Reward designs that would be fun to interact with in a physics sandbox."
    ),
    "Coherence": (
        "Evaluate whether all parts of this game object design work together "
        "thematically. The name, tags, behaviors, and visual description should "
        "tell a consistent story. A 'Fire Dragon' with FROZEN tags is incoherent. "
        "A 'Healing Mushroom' with DEAL_DAMAGE behavior is incoherent. The visual "
        "description should match the tags — a GLOWING object should be described "
        "as luminous or bright, not dull or dark. A LIQUID object should not be "
        "described as a solid block. Reward designs where every element reinforces "
        "the same theme."
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
