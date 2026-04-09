"""Creature quality gate: does evaluate_creature_behaviors() produce correct behavior?

One Case per creature (grouped targets evaluated in a single LLM call).
Standalone pydantic-evals script — no pytest required.
Run: make eval-creature
"""

from __future__ import annotations

import asyncio
import io
import sys

# Force UTF-8 stdout for Rich output on Windows (cp1252 can't render box chars)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dataclasses import dataclass
from typing import Any

import structlog
from app.cache.scene import SceneCache
from app.creator.llm import ask_int, reset_agents
from app.engine.creature import evaluate_creature_behaviors
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from evals.helpers import (
    SummaryEvaluator,
    generate_summary,
    get_run_dir,
    load_suite,
    make_blueprint,
    parse_eval_args,
    save_report,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class TargetExpectation(BaseModel):
    target_name: str
    expected: dict[str, Any]
    note: str


class CreatureInput(BaseModel):
    creature_name: str
    targets: list[TargetExpectation]


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


@dataclass(repr=False)
class CreatureBehaviorEvaluator(Evaluator[CreatureInput, dict[str, Any], None]):
    """Check creature behaviors against fixture expectations.

    Supports:
      - list of acceptable values: actual must be in the list
      - {min, max} dict: range check (min <= actual <= max)
      - exact value: actual must equal expected
    Failures include a reason string showing actual vs expected.
    """

    def evaluate(
        self, ctx: EvaluatorContext[CreatureInput, dict[str, Any], None]
    ) -> dict[str, EvaluationReason]:
        results: dict[str, EvaluationReason] = {}
        creature = ctx.inputs.creature_name

        for te in ctx.inputs.targets:
            target = te.target_name
            prefix = f"{creature}_vs_{target}"

            if target not in ctx.output:
                for field in te.expected:
                    results[f"{prefix}.{field}"] = EvaluationReason(
                        value=False, reason=f"target '{target}' missing from output"
                    )
                continue

            behavior = ctx.output[target]
            for field, expected_val in te.expected.items():
                actual = behavior.get(field)
                if isinstance(expected_val, dict) and "min" in expected_val:
                    lo, hi = expected_val["min"], expected_val["max"]
                    passed = lo <= actual <= hi
                    results[f"{prefix}.{field}"] = EvaluationReason(
                        value=passed,
                        reason=None if passed else f"got {actual}, expected [{lo}, {hi}]",
                    )
                elif isinstance(expected_val, list):
                    passed = actual in expected_val
                    results[f"{prefix}.{field}"] = EvaluationReason(
                        value=passed,
                        reason=None if passed else f"got {actual}, expected one of {expected_val}",
                    )
                else:
                    passed = actual == expected_val
                    results[f"{prefix}.{field}"] = EvaluationReason(
                        value=passed,
                        reason=None if passed else f"got {actual}, expected {expected_val}",
                    )

        return results


# ---------------------------------------------------------------------------
# Build dataset
# ---------------------------------------------------------------------------


def build_dataset() -> Dataset[CreatureInput, dict[str, Any], None]:
    suite = load_suite()
    cases = []

    for entry in suite["creatures"]:
        creature_name = entry["creature"]
        targets = [
            TargetExpectation(
                target_name=t["name"],
                expected=t["expected"],
                note=t.get("note", ""),
            )
            for t in entry["targets"]
        ]

        cases.append(
            Case(
                name=creature_name,
                inputs=CreatureInput(creature_name=creature_name, targets=targets),
            )
        )

    return Dataset(
        cases=cases,
        evaluators=[CreatureBehaviorEvaluator()],
        report_evaluators=[SummaryEvaluator()],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    args = parse_eval_args()
    run_dir = get_run_dir()

    reset_agents()

    # Health check
    result = await ask_int("Reply with 1. Just the number.", 0, 1, -1)
    if result == -1:
        logger.error("LLM unreachable. Start local server with `make gpu` or configure cloud.")
        sys.exit(1)
    reset_agents()

    scene = SceneCache()

    async def task(inputs: CreatureInput) -> dict[str, Any]:
        creature_bp = make_blueprint(inputs.creature_name, autonomous=True)
        target_bps = [make_blueprint(t.target_name) for t in inputs.targets]
        target_names = [t.name for t in target_bps]

        results = await evaluate_creature_behaviors(
            creature=creature_bp,
            targets=target_bps,
            scene_inventory=target_names,
            scene=scene,
        )

        return {name: behavior.to_dict() for name, behavior in results.items()}

    dataset = build_dataset()
    report = await dataset.evaluate(task, name="creature", repeat=args.repeat)
    report.print(include_reasons=True)
    path = save_report(report, run_dir)
    summary = generate_summary(run_dir)
    print(f"\nResults saved to {path}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
