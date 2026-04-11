"""Behavior quality gate: does evaluate_behaviors() produce correct behavior?
Also tests screen_pairs() for screening coverage.

One Case per subject (grouped targets evaluated in a single LLM call).
Standalone pydantic-evals script — no pytest required.
Run: make eval-behavior
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
from app.cache.scene import BehaviorCache
from app.config import settings
from app.creator.llm import ask_int, reset_agents
from app.engine.behavior import evaluate_behaviors, screen_pairs
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
# Screening types & evaluator
# ---------------------------------------------------------------------------


class ScreeningInput(BaseModel):
    new_object: str
    scene: list[str]


class ScreeningExpected(BaseModel):
    should_include: list[str]
    should_exclude: list[str] = []
    note: str = ""


@dataclass(repr=False)
class ScreeningEvaluator(Evaluator[ScreeningInput, list[str], ScreeningExpected]):
    """Check that screening returns expected interesting pairs."""

    def evaluate(
        self, ctx: EvaluatorContext[ScreeningInput, list[str], ScreeningExpected]
    ) -> dict[str, EvaluationReason]:
        assert ctx.metadata is not None
        result_lower = [r.lower() for r in ctx.output]
        checks: dict[str, EvaluationReason] = {}

        for name in ctx.metadata.should_include:
            found = name.lower() in result_lower
            checks[f"includes_{name}"] = EvaluationReason(
                value=found,
                reason=None if found else f"'{name}' not in results: {ctx.output}",
            )

        for name in ctx.metadata.should_exclude:
            absent = name.lower() not in result_lower
            checks[f"excludes_{name}"] = EvaluationReason(
                value=absent,
                reason=None if absent else f"'{name}' unexpectedly in results: {ctx.output}",
            )

        return checks


# ---------------------------------------------------------------------------
# Behavior types & evaluator
# ---------------------------------------------------------------------------


class TargetExpectation(BaseModel):
    target_name: str
    expected: dict[str, Any]
    note: str


class BehaviorInput(BaseModel):
    subject_name: str
    targets: list[TargetExpectation]


@dataclass(repr=False)
class BehaviorEvaluator(Evaluator[BehaviorInput, dict[str, Any], None]):
    """Check behavior results against fixture expectations.

    Supports:
      - list of acceptable values: actual must be in the list
      - {min, max} dict: range check (min <= actual <= max)
      - exact value: actual must equal expected
    Failures include a reason string showing actual vs expected.
    """

    def evaluate(
        self, ctx: EvaluatorContext[BehaviorInput, dict[str, Any], None]
    ) -> dict[str, EvaluationReason]:
        results: dict[str, EvaluationReason] = {}
        subject = ctx.inputs.subject_name

        for te in ctx.inputs.targets:
            target = te.target_name
            prefix = f"{subject}_vs_{target}"

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
# Build datasets
# ---------------------------------------------------------------------------


def build_screening_dataset() -> Dataset[ScreeningInput, list[str], ScreeningExpected]:
    suite = load_suite()
    cases = [
        Case(
            name=f"screen: {entry['new_object']}",
            inputs=ScreeningInput(
                new_object=entry["new_object"],
                scene=entry["scene"],
            ),
            metadata=ScreeningExpected(
                should_include=entry["should_include"],
                should_exclude=entry.get("should_exclude", []),
                note=entry.get("note", ""),
            ),
        )
        for entry in suite["screening"]
    ]

    return Dataset(
        cases=cases, evaluators=[ScreeningEvaluator()], report_evaluators=[SummaryEvaluator()]
    )


def build_behavior_dataset() -> Dataset[BehaviorInput, dict[str, Any], None]:
    suite = load_suite()
    cases = []

    for entry in suite["behaviors"]:
        subject_name = entry["subject"]
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
                name=subject_name,
                inputs=BehaviorInput(subject_name=subject_name, targets=targets),
            )
        )

    return Dataset(
        cases=cases,
        evaluators=[BehaviorEvaluator()],
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

    # Disable creation cache so each repeat makes fresh LLM calls
    settings.creation_cache_enabled = False

    # --- Screening eval ---
    async def screening_task(inputs: ScreeningInput) -> list[str]:
        new_bp = make_blueprint(inputs.new_object)
        scene_bps = [make_blueprint(name) for name in inputs.scene]
        return await screen_pairs(new_bp, scene_bps)

    screening_ds = build_screening_dataset()
    screening_report = await screening_ds.evaluate(
        screening_task,
        name="screening",
        repeat=args.repeat,
    )
    screening_report.print(include_reasons=True)
    save_report(screening_report, run_dir)

    # --- Behavior eval ---
    async def behavior_task(inputs: BehaviorInput) -> dict[str, Any]:
        scene = BehaviorCache()  # fresh per case — no shared state between cases/repeats
        subject_bp = make_blueprint(inputs.subject_name)
        target_bps = [make_blueprint(t.target_name) for t in inputs.targets]

        # Build target_states from archetype initial_states for state-aware eval
        target_states: dict[str, list[int]] = {}
        for bp in target_bps:
            if bp.initial_states:
                target_states[bp.name] = bp.initial_states

        results = await evaluate_behaviors(
            subject=subject_bp,
            targets=target_bps,
            scene=scene,
            target_states=target_states or None,
        )

        return {name: behavior.to_dict() for name, behavior in results.items()}

    behavior_ds = build_behavior_dataset()
    behavior_report = await behavior_ds.evaluate(
        behavior_task,
        name="behavior",
        repeat=args.repeat,
    )
    behavior_report.print(include_reasons=True)
    save_report(behavior_report, run_dir)

    summary = generate_summary(run_dir)
    print(f"\nResults saved to {run_dir}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
