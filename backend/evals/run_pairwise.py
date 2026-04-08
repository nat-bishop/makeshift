"""Pairwise quality gate: does evaluate_pair() produce sensible interactions?
Also tests screen_pairs() for screening coverage.

Standalone pydantic-evals script — no pytest required.
Run: make eval-pairwise
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
from app.cache.store import CacheStore
from app.config import settings
from app.creator.llm import ask_int, reset_agents
from app.engine.pairwise import evaluate_pair, screen_pairs
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from evals.helpers import (
    STATE_STRING_TO_CODE,
    SummaryEvaluator,
    in_range,
    load_suite,
    make_blueprint,
    orient_expected,
    save_report,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Pairwise types & evaluator
# ---------------------------------------------------------------------------


class PairwiseInput(BaseModel):
    pair: list[str]


class PairwiseExpected(BaseModel):
    expected: dict[str, Any]
    note: str


@dataclass(repr=False)
class PairwiseEvaluator(Evaluator[PairwiseInput, dict[str, Any], PairwiseExpected]):
    """Check pairwise results against fixture expectations.

    Ranges [lo, hi] are binary pass/fail.
    Exact fields (state, continuous) are exact match.
    State fields accept a list of acceptable values.
    force_b is signed (-100 to 100, negative=pull).
    Failures include a reason string showing actual vs expected.
    """

    def evaluate(
        self, ctx: EvaluatorContext[PairwiseInput, dict[str, Any], PairwiseExpected]
    ) -> dict[str, EvaluationReason]:
        assert ctx.metadata is not None
        result = ctx.output
        expected = ctx.metadata.expected
        checks: dict[str, EvaluationReason] = {}

        def _reason(passed: bool, actual: object, exp: object) -> EvaluationReason:
            return EvaluationReason(
                value=passed, reason=None if passed else f"got {actual}, expected {exp}"
            )

        # Damage ranges
        for field in ("damage_a", "damage_b"):
            if field in expected:
                val = expected[field]
                actual = result[field]
                if isinstance(val, list):
                    lo, hi = float(val[0]), float(val[1])
                    checks[field] = _reason(in_range(float(actual), lo, hi), actual, f"[{lo}, {hi}]")
                else:
                    checks[field] = _reason(actual == val, actual, val)

        # State changes
        for field in ("state_a", "state_b"):
            result_field = field.replace("state_", "state_change_")
            if field in expected:
                val = expected[field]
                actual = result[result_field]
                if isinstance(val, list):
                    acceptable_codes = {STATE_STRING_TO_CODE[s] for s in val}
                    checks[field] = _reason(actual in acceptable_codes, actual, val)
                else:
                    expected_code = STATE_STRING_TO_CODE[val]
                    checks[field] = _reason(actual == expected_code, actual, val)

        # Force range (signed: negative=pull, positive=push)
        if "force_b" in expected:
            val = expected["force_b"]
            actual = result["force_b"]
            if isinstance(val, list):
                lo, hi = float(val[0]), float(val[1])
                checks["force_b"] = _reason(
                    in_range(float(actual), lo, hi), actual, f"[{lo}, {hi}]"
                )
            else:
                checks["force_b"] = _reason(actual == val, actual, val)

        # Continuous
        if "continuous" in expected:
            actual = result["continuous"]
            checks["continuous"] = _reason(actual == expected["continuous"], actual, expected["continuous"])

        return checks


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
# Build datasets
# ---------------------------------------------------------------------------


def build_pairwise_dataset() -> Dataset[PairwiseInput, dict[str, Any], PairwiseExpected]:
    suite = load_suite()
    cases = []

    for entry in suite["pairs"]:
        pair = entry["pair"]
        raw_expected = entry["expected"]
        oriented = orient_expected(pair, raw_expected)

        cases.append(
            Case(
                name=f"{pair[0]} vs {pair[1]}",
                inputs=PairwiseInput(pair=pair),
                metadata=PairwiseExpected(expected=oriented, note=entry.get("note", "")),
            )
        )

    return Dataset(
        cases=cases, evaluators=[PairwiseEvaluator()], report_evaluators=[SummaryEvaluator()]
    )


def build_screening_dataset() -> Dataset[ScreeningInput, list[str], ScreeningExpected]:
    suite = load_suite()
    cases = []

    for entry in suite["screening"]:
        cases.append(
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
        )

    return Dataset(
        cases=cases, evaluators=[ScreeningEvaluator()], report_evaluators=[SummaryEvaluator()]
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
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
    scene = SceneCache()

    # --- Pairwise eval ---
    async def pairwise_task(inputs: PairwiseInput) -> dict[str, Any]:
        bp_a = make_blueprint(inputs.pair[0])
        bp_b = make_blueprint(inputs.pair[1])
        pr = await evaluate_pair(bp_a, bp_b, cache, scene)
        return pr.to_dict()

    pairwise_ds = build_pairwise_dataset()
    pairwise_report = await pairwise_ds.evaluate(
        pairwise_task, name="pairwise", repeat=5,
    )
    pairwise_report.print(include_reasons=True)
    path = save_report(pairwise_report)
    print(f"\nResults saved to {path}")

    # --- Screening eval ---
    async def screening_task(inputs: ScreeningInput) -> list[str]:
        new_bp = make_blueprint(inputs.new_object)
        scene_bps = [make_blueprint(name) for name in inputs.scene]
        return await screen_pairs(new_bp, scene_bps)

    screening_ds = build_screening_dataset()
    screening_report = await screening_ds.evaluate(
        screening_task, name="screening", repeat=5,
    )
    screening_report.print(include_reasons=True)
    path = save_report(screening_report)
    print(f"\nResults saved to {path}")

    await cache.close()


if __name__ == "__main__":
    asyncio.run(main())
