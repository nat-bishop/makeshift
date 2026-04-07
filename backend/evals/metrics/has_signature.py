"""Has Behaviors evaluator — deterministic, no LLM call.

Flags CREATURE objects that have no explicit behaviors (only the
default "investigate nearby objects" implied behavior).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class HasSignatureEvaluator(Evaluator[str, str, object]):
    """Check if CREATURE objects have explicit behaviors for personality.

    Returns 1.0 if the object has behaviors or is not a CREATURE.
    Returns 0.0 if CREATURE with no explicit behaviors.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Has Signature": EvaluationReason(value=1.0, reason="Not valid JSON")}

        categories = data.get("categories", [])
        if "CREATURE" not in categories:
            return {
                "Has Signature": EvaluationReason(value=1.0, reason="Not a CREATURE")
            }

        behaviors = data.get("behaviors", [])
        if behaviors:
            verbs = [b.get("verb", "") for b in behaviors if isinstance(b, dict)]
            return {
                "Has Signature": EvaluationReason(
                    value=1.0, reason=f"Has {len(behaviors)} behaviors: {', '.join(verbs)}"
                )
            }

        return {
            "Has Signature": EvaluationReason(
                value=0.0, reason="CREATURE with no explicit behaviors"
            )
        }
