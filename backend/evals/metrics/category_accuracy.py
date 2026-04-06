"""Category Accuracy evaluator — deterministic, no LLM call.

Checks if the LLM picked the expected categories (order-independent set match).
Cases with no expected_categories are skipped (score 1.0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class CategoryAccuracyEvaluator(Evaluator[str, str, object]):
    """Check if the output categories match the expected categories from case metadata.

    Score = 1.0 for exact set match or no expectation, 0.0 for mismatch.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        expected: list[str] = []
        if ctx.metadata and hasattr(ctx.metadata, "expected_categories"):
            expected = list(ctx.metadata.expected_categories)

        if not expected:
            return {
                "Category Accuracy": EvaluationReason(
                    value=1.0, reason="No expected categories"
                )
            }

        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {
                "Category Accuracy": EvaluationReason(value=0.0, reason="Not valid JSON")
            }

        actual = set(data.get("categories", []))
        expected_set = set(expected)
        if actual == expected_set:
            return {
                "Category Accuracy": EvaluationReason(
                    value=1.0, reason=f"Correct: {sorted(actual)}"
                )
            }

        return {
            "Category Accuracy": EvaluationReason(
                value=0.0,
                reason=f"Expected {sorted(expected_set)}, got {sorted(actual)}",
            )
        }
