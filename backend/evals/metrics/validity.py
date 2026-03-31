"""Deterministic validity evaluator — no LLM call.

Checks structural correctness of CreatorOutputSpec against
game rules: contradictions, behavior parsing, count limits, etc.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

from app.models.behaviors import (
    BehaviorParseError,
    parse_behavior_string,
)
from app.models.tags import (
    TAG_CONTRADICTIONS,
    Tag,
)
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class ValidityEvaluator(Evaluator[str, str, object]):
    """Deterministic checks on structured output correctness.

    JSON parse failure is catastrophic (score 0.0). Other checks
    are severity-weighted: structural issues (tags, behaviors)
    weigh more than cosmetic ones (name length).
    """

    # Severity weights for each check (higher = more important)
    CHECK_WEIGHTS: dict[str, int] = dataclasses.field(default_factory=lambda: {
        "valid_tag_enums": 2,
        "tag_count": 1,
        "no_contradictions": 2,
        "behaviors_parse": 2,
        "name_length": 1,
    })

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""

        # 1. Parse as JSON — gate check, instant 0.0 on failure
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Validity": EvaluationReason(value=0.0, reason="Output is not valid JSON")}

        checks: dict[str, bool] = {}

        # 2. Extract and validate tags
        raw_tags = data.get("tags", [])
        try:
            tags = [Tag(t) for t in raw_tags]
        except (ValueError, KeyError):
            tags = []
            checks["valid_tag_enums"] = False

        if "valid_tag_enums" not in checks:
            checks["valid_tag_enums"] = True

        # 3. Tag count (2-6)
        checks["tag_count"] = 2 <= len(raw_tags) <= 6

        # 4. No contradictions
        if checks["valid_tag_enums"]:
            tag_set = set(tags)
            checks["no_contradictions"] = not any(pair <= tag_set for pair in TAG_CONTRADICTIONS)
        else:
            checks["no_contradictions"] = False

        # 5. Behaviors parse
        raw_behaviors = data.get("behaviors", [])
        all_parse = True
        for b in raw_behaviors:
            try:
                parse_behavior_string(str(b))
            except (BehaviorParseError, ValueError, Exception):
                all_parse = False
                break
        checks["behaviors_parse"] = all_parse

        # 6. Name length (1-3 words)
        name = data.get("name", "")
        words = str(name).strip().split()
        checks["name_length"] = 1 <= len(words) <= 3

        # Weighted scoring
        weighted_passed = sum(
            self.CHECK_WEIGHTS.get(k, 1) for k, v in checks.items() if v
        )
        weighted_total = sum(self.CHECK_WEIGHTS.get(k, 1) for k in checks)
        score = weighted_passed / weighted_total if weighted_total > 0 else 0.0

        failed = [k for k, v in checks.items() if not v]
        reason = f"Failed checks: {', '.join(failed)}" if failed else "All validity checks passed"

        return {"Validity": EvaluationReason(value=score, reason=reason)}
