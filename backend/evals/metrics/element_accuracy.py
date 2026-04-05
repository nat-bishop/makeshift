"""Element Accuracy evaluator — deterministic, no LLM call.

Checks if the LLM picked the expected element (or correctly omitted it).
Cases with no expected_element are skipped (score 1.0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class ElementAccuracyEvaluator(Evaluator[str, str, object]):
    """Check if the output element matches the expected element from case metadata.

    Score = 1.0 for exact match or no expectation, 0.0 for mismatch.
    expected_element=None in metadata means "skip" (unpredictable).
    expected_element="" means "should be null/absent".
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        expected: str | None = None
        if ctx.metadata and hasattr(ctx.metadata, "expected_element"):
            expected = ctx.metadata.expected_element

        if expected is None:
            return {
                "Element Accuracy": EvaluationReason(
                    value=1.0, reason="No expected element"
                )
            }

        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {
                "Element Accuracy": EvaluationReason(value=0.0, reason="Not valid JSON")
            }

        actual = data.get("element") or ""

        if expected == "" and actual == "":
            return {
                "Element Accuracy": EvaluationReason(
                    value=1.0, reason="Correct: no element"
                )
            }

        if actual == expected:
            return {
                "Element Accuracy": EvaluationReason(
                    value=1.0, reason=f"Correct: {actual}"
                )
            }

        expected_display = expected or "(none)"
        actual_display = actual or "(none)"
        return {
            "Element Accuracy": EvaluationReason(
                value=0.0, reason=f"Expected {expected_display}, got {actual_display}"
            )
        }
