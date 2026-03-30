"""Deterministic validity evaluator — no LLM call.

Checks structural correctness of CreatorOutputSpec against
game rules: budget, contradictions, behavior parsing, etc.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.behaviors import (
    BEHAVIOR_BUDGET,
    BehaviorParseError,
    compute_spec_cost,
    parse_behavior_string,
)
from app.models.tags import (
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    Tag,
)
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class ValidityEvaluator(Evaluator[str, str, object]):
    """Deterministic checks on structured output correctness.

    Scores 1.0 only if all 8 checks pass. Each failed check
    deducts 1/8 from the score.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""
        checks: dict[str, bool] = {}

        # 1. Parse as JSON
        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Validity": EvaluationReason(value=0.0, reason="Output is not valid JSON")}
        checks["json_parse"] = True

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

        # 4. Tag budget <= 10
        if checks["valid_tag_enums"]:
            cost = sum(TAG_POWER_COSTS.get(t, 0) for t in tags)
            checks["tag_budget"] = cost <= OBJECT_TAG_BUDGET
        else:
            checks["tag_budget"] = False

        # 5. No contradictions
        if checks["valid_tag_enums"]:
            tag_set = set(tags)
            checks["no_contradictions"] = not any(pair <= tag_set for pair in TAG_CONTRADICTIONS)
        else:
            checks["no_contradictions"] = False

        # 6. Behaviors parse
        raw_behaviors = data.get("behaviors", [])
        parsed_specs = []
        all_parse = True
        for b in raw_behaviors:
            try:
                parsed_specs.append(parse_behavior_string(str(b)))
            except (BehaviorParseError, ValueError, Exception):
                all_parse = False
                break
        checks["behaviors_parse"] = all_parse

        # 7. Behavior budget <= 8
        if all_parse and parsed_specs:
            bcost = sum(compute_spec_cost(s) for s in parsed_specs)
            checks["behavior_budget"] = bcost <= BEHAVIOR_BUDGET
        else:
            checks["behavior_budget"] = True  # No behaviors = no budget issue

        # 8. Name length (1-3 words)
        name = data.get("name", "")
        words = str(name).strip().split()
        checks["name_length"] = 1 <= len(words) <= 3

        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        score = passed / total if total > 0 else 0.0

        failed = [k for k, v in checks.items() if not v]
        reason = f"Failed checks: {', '.join(failed)}" if failed else "All validity checks passed"

        return {"Validity": EvaluationReason(value=score, reason=reason)}
