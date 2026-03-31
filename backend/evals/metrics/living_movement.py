"""Has Signature evaluator — deterministic, no LLM call.

Flags LIVING objects that have no signature behavior (only generic
tag-implied behaviors like wander/chase). These objects work but
lack unique personality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.tags import Tag
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class HasSignatureEvaluator(Evaluator[str, str, object]):
    """Check if LIVING objects have a signature behavior for personality.

    LIVING objects get implied behaviors (wander, chase) from tags automatically.
    A signature behavior adds unique personality beyond the defaults.

    Returns 1.0 if the object has a signature or is not LIVING.
    Returns 0.0 if LIVING with no signature behavior.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Has Signature": EvaluationReason(value=1.0, reason="Not valid JSON")}

        raw_tags = data.get("tags", [])
        if Tag.LIVING.value not in raw_tags:
            return {
                "Has Signature": EvaluationReason(value=1.0, reason="Not a LIVING object")
            }

        signature = data.get("signature")
        if signature:
            return {
                "Has Signature": EvaluationReason(
                    value=1.0, reason=f"Has signature: {signature}"
                )
            }

        return {
            "Has Signature": EvaluationReason(
                value=0.0, reason="LIVING object with no signature behavior"
            )
        }
