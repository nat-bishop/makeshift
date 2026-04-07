"""Deterministic validity evaluator — no LLM call.

V2: checks substance, element, tags (0-3), behaviors, name, visual.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

from app.models.blueprint import BehaviorVerb
from app.models.substances import Element, Substance
from app.models.tags import LLM_VISIBLE_TAGS, Category
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

_V2_TAG_VALUES = frozenset(t.value for t in LLM_VISIBLE_TAGS)
_SUBSTANCE_VALUES = frozenset(s.value for s in Substance)
_ELEMENT_VALUES = frozenset(e.value for e in Element)
_VERB_VALUES = frozenset(v.value for v in BehaviorVerb)
_CATEGORY_VALUES = frozenset(c.value for c in Category)


@dataclass
class ValidityEvaluator(Evaluator[str, str, object]):
    """Deterministic checks on V2 structured output correctness."""

    CHECK_WEIGHTS: dict[str, int] = dataclasses.field(default_factory=lambda: {
        "valid_substance": 2,
        "valid_element": 1,
        "valid_categories": 1,
        "valid_tags": 2,
        "tag_count": 1,
        "valid_behaviors": 1,
        "name_length": 1,
        "visual_desc_length": 1,
    })

    def evaluate(self, ctx: EvaluatorContext[str, str, object]) -> dict[str, EvaluationReason]:
        output_text = ctx.output or ""

        try:
            data = json.loads(output_text)
        except (json.JSONDecodeError, TypeError):
            return {"Validity": EvaluationReason(value=0.0, reason="Output is not valid JSON")}

        checks: dict[str, bool] = {}

        # Substance (required)
        checks["valid_substance"] = data.get("substance", "") in _SUBSTANCE_VALUES

        # Element (optional)
        element = data.get("element")
        checks["valid_element"] = element is None or element in _ELEMENT_VALUES

        # Categories (0-7, valid Category values)
        raw_cats = data.get("categories", [])
        checks["valid_categories"] = all(c in _CATEGORY_VALUES for c in raw_cats)

        # Tags (0-3, V2 visible set)
        raw_tags = data.get("tags", [])
        checks["tag_count"] = 0 <= len(raw_tags) <= 3
        checks["valid_tags"] = all(t in _V2_TAG_VALUES for t in raw_tags)

        # Behaviors (0-4, valid verbs)
        behaviors = data.get("behaviors", [])
        checks["valid_behaviors"] = all(
            isinstance(b, dict) and b.get("verb", "") in _VERB_VALUES and b.get("target_description")
            for b in behaviors
        ) and len(behaviors) <= 4

        # Name length (1-3 words)
        name = data.get("name", "")
        words = str(name).strip().split()
        checks["name_length"] = 1 <= len(words) <= 3

        # Visual description length (>=40 chars)
        vd = data.get("visual_descriptor", {})
        visual_desc = vd.get("visual_description", "") if isinstance(vd, dict) else ""
        checks["visual_desc_length"] = len(visual_desc) >= 40

        # Weighted scoring
        weighted_passed = sum(
            self.CHECK_WEIGHTS.get(k, 1) for k, v in checks.items() if v
        )
        weighted_total = sum(self.CHECK_WEIGHTS.get(k, 1) for k in checks)
        score = weighted_passed / weighted_total if weighted_total > 0 else 0.0

        failed = [k for k, v in checks.items() if not v]
        reason = f"Failed checks: {', '.join(failed)}" if failed else "All validity checks passed"

        return {"Validity": EvaluationReason(value=score, reason=reason)}
