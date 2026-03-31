"""Interaction Surface evaluator — deterministic, no LLM call.

Counts how many game rules an object's tag set could participate in,
measuring its potential for emergent gameplay interactions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.engine.rules_data import ALL_RULES
from app.models.tags import Tag
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


def compute_interaction_surface(tags: set[Tag]) -> tuple[int, list[str]]:
    """Count unique rules this tag set can participate in (as either side).

    Returns (rule_count, list_of_matching_rule_names).
    """
    matched: list[str] = []
    for rule in ALL_RULES:
        # Can this object be the A-side?
        a_match = rule.tags_required_a <= tags
        # Can this object be the B-side?
        b_match = rule.tags_required_b <= tags if rule.tags_required_b else False
        if a_match or b_match:
            matched.append(rule.name)
    return len(matched), matched


@dataclass
class InteractionSurfaceEvaluator(Evaluator[str, str, object]):
    """Counts how many game rules an object's tags could trigger.

    Returns the raw count (0-53), not a 0-1 normalized score.
    Higher means more potential for emergent interactions.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {
                "Interaction Surface": EvaluationReason(value=0.0, reason="Not valid JSON")
            }

        raw_tags = data.get("tags", [])
        try:
            tags = {Tag(t) for t in raw_tags}
        except (ValueError, KeyError):
            return {
                "Interaction Surface": EvaluationReason(
                    value=0.0, reason="Invalid tag values"
                )
            }

        count, names = compute_interaction_surface(tags)
        reason = f"{count} rules: {', '.join(names)}" if names else "No rule matches"
        return {"Interaction Surface": EvaluationReason(value=float(count), reason=reason)}
