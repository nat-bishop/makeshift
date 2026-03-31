"""Living Movement evaluator — deterministic, no LLM call.

Flags LIVING objects that have no movement behaviors.
Informational metric, not a quality penalty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.behaviors import BehaviorAction, BehaviorParseError, parse_behavior_string
from app.models.tags import Tag
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

_MOVEMENT_ACTIONS = frozenset({
    BehaviorAction.MOVE_TOWARD,
    BehaviorAction.MOVE_AWAY,
    BehaviorAction.PATROL,
})


@dataclass
class LivingMovementEvaluator(Evaluator[str, str, object]):
    """Check if LIVING objects have at least one movement behavior.

    Returns 1.0 if the object has movement or is not LIVING.
    Returns 0.0 if LIVING with no movement behaviors.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Living Movement": EvaluationReason(value=1.0, reason="Not valid JSON")}

        raw_tags = data.get("tags", [])
        if Tag.LIVING.value not in raw_tags:
            return {
                "Living Movement": EvaluationReason(value=1.0, reason="Not a LIVING object")
            }

        # Check behaviors for movement actions
        for b in data.get("behaviors", []):
            try:
                spec = parse_behavior_string(str(b))
                if spec.action in _MOVEMENT_ACTIONS:
                    return {
                        "Living Movement": EvaluationReason(
                            value=1.0, reason=f"Has {spec.action} behavior"
                        )
                    }
            except (BehaviorParseError, ValueError):
                continue

        return {
            "Living Movement": EvaluationReason(
                value=0.0, reason="LIVING object with no movement behaviors"
            )
        }
