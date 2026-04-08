"""Creation quality gate: does create_object() produce reasonable physics?

Standalone pydantic-evals script — no pytest required.
Run: make eval-creation
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys

# Force UTF-8 stdout for Rich output on Windows (cp1252 can't render box chars)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dataclasses import dataclass
from typing import Any

import structlog
from app.cache.store import CacheStore
from app.config import settings
from app.creator.llm import ask_int, reset_agents
from app.creator.pipeline import create_object
from app.models.blueprint import GameObjectBlueprint
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, LLMJudge

from evals.helpers import SummaryEvaluator, in_range, load_suite, save_report

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

# Field name -> blueprint attribute path
FIELD_TO_ATTR: dict[str, str] = {
    "mass_kg": "physics.mass_kg",
    "height_cm": "physics.height_cm",
    "friction": "physics.friction",
    "bounce": "physics.bounce",
    "gravity": "physics.gravity",
    "armor": "destructibility.armor",
    "hp": "destructibility.hp",
    "indestructible": "destructibility.indestructible",
}


def _get_nested(obj: object, dotted_path: str) -> object:
    result = obj
    for part in dotted_path.split("."):
        result = getattr(result, part)
    return result


@dataclass(repr=False)
class CreationEvaluator(Evaluator[str, GameObjectBlueprint, dict[str, Any]]):
    """Check creation output against per-object expected values.

    Ranges [lo, hi] are binary pass/fail. Exact values (bool, int) are exact match.
    Failures include a reason string showing actual vs expected.
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, GameObjectBlueprint, dict[str, Any]]
    ) -> dict[str, EvaluationReason]:
        if ctx.metadata is None:
            return {}

        bp = ctx.output
        expected = ctx.metadata
        results: dict[str, EvaluationReason] = {}

        for field, val in expected.items():
            if isinstance(val, list) and len(val) == 2:
                attr_path: str = FIELD_TO_ATTR.get(field, field)
                actual_num = float(_get_nested(bp, attr_path))  # type: ignore[arg-type]
                lo, hi = float(val[0]), float(val[1])
                passed = in_range(actual_num, lo, hi)
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {actual_num}, expected [{lo}, {hi}]",
                )
            elif isinstance(val, bool):
                attr_path = FIELD_TO_ATTR.get(field, field)
                actual = _get_nested(bp, attr_path)
                passed = actual == val
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {actual}, expected {val}",
                )
            elif isinstance(val, int):
                actual = getattr(bp, field)
                passed = actual == val
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {actual}, expected {val}",
                )

        return results


# ---------------------------------------------------------------------------
# Build dataset
# ---------------------------------------------------------------------------


def build_dataset(use_judge: bool = False) -> Dataset[str, GameObjectBlueprint, dict[str, Any]]:
    suite = load_suite()
    cases = []

    for entry in suite["creation_tests"]:
        obj_name = entry["name"]
        expected = entry.get("expected", {})

        per_case_evals: tuple = ()
        if use_judge:
            per_case_evals = (
                LLMJudge(
                    rubric=(
                        f"The visual description accurately describes '{obj_name}' "
                        f"for a 2D sprite artist. It mentions shape, colors, and materials."
                    ),
                    model="google-gla:gemini-3.1-flash-lite-preview",
                    include_input=True,
                ),
            )

        cases.append(
            Case(
                name=obj_name,
                inputs=obj_name,
                metadata=expected,
                evaluators=per_case_evals,
            )
        )

    return Dataset(
        cases=cases,
        evaluators=[CreationEvaluator()],
        report_evaluators=[SummaryEvaluator()],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge", action="store_true", help="Enable LLM judge",
    )
    args = parser.parse_args()

    reset_agents()

    # Health check
    result = await ask_int("Reply with 1. Just the number.", 0, 1, -1)
    if result == -1:
        logger.error("LLM unreachable. Start local server with `make gpu` or configure cloud.")
        sys.exit(1)
    reset_agents()

    # Disable creation cache so each repeat makes fresh LLM calls
    settings.creation_cache_enabled = False

    cache = await CacheStore.open(":memory:")

    async def task(inputs: str) -> GameObjectBlueprint:
        return await create_object(inputs, cache)

    dataset = build_dataset(use_judge=args.judge)
    report = await dataset.evaluate(task, name="creation", repeat=5)
    report.print(include_reasons=True)
    path = save_report(report)
    print(f"\nResults saved to {path}")

    await cache.close()


if __name__ == "__main__":
    asyncio.run(main())
