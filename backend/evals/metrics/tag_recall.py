"""Tag Recall evaluator — deterministic, no LLM call.

Measures how many of the expected tags actually appear in the output.
Cases with no expected_tags are skipped (score 1.0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class TagRecallEvaluator(Evaluator[str, str, object]):
    """Check if the output includes the expected tags from case metadata.

    Score = |actual ∩ expected| / |expected|.
    Returns 1.0 for cases with no expected tags (nothing to check).
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        expected: list[str] = []
        if ctx.metadata and hasattr(ctx.metadata, "expected_tags"):
            expected = ctx.metadata.expected_tags or []

        if not expected:
            return {"Tag Recall": EvaluationReason(value=1.0, reason="No expected tags defined")}

        output_text = ctx.output or ""
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Tag Recall": EvaluationReason(value=0.0, reason="Not valid JSON")}

        actual_tags = set(data.get("tags", []))
        hits = [t for t in expected if t in actual_tags]
        missing = [t for t in expected if t not in actual_tags]
        score = len(hits) / len(expected)

        if missing:
            reason = f"Hit {len(hits)}/{len(expected)}, missing: {', '.join(missing)}"
        else:
            reason = f"All {len(expected)} expected tags present"

        return {"Tag Recall": EvaluationReason(value=score, reason=reason)}
