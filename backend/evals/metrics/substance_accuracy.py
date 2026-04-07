"""Substance Accuracy evaluator — deterministic, no LLM call.

Checks if the LLM picked the expected substance.
Cases with no expected_substance are skipped (score 1.0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class SubstanceAccuracyEvaluator(Evaluator[str, str, object]):
    """Check if the output substance matches the expected substance from case metadata.

    Score = 1.0 for exact match or no expectation, 0.0 for mismatch.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        expected: str | None = None
        if ctx.metadata and hasattr(ctx.metadata, "expected_substance"):
            expected = ctx.metadata.expected_substance

        if expected is None:
            return {
                "Substance Accuracy": EvaluationReason(
                    value=1.0, reason="No expected substance"
                )
            }

        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {
                "Substance Accuracy": EvaluationReason(value=0.0, reason="Not valid JSON")
            }

        actual = data.get("substance", "")
        if actual == expected:
            return {
                "Substance Accuracy": EvaluationReason(
                    value=1.0, reason=f"Correct: {actual}"
                )
            }

        return {
            "Substance Accuracy": EvaluationReason(
                value=0.0, reason=f"Expected {expected}, got {actual}"
            )
        }
