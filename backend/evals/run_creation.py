"""Creation quality gate: does create_object() produce reasonable physics?

Standalone pydantic-evals script — no pytest required.
Run: make eval-creation
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
from app.cache.store import CacheStore
from app.config import settings
from app.creator.llm import ask_int, reset_agents
from app.creator.pipeline import create_object
from app.models.blueprint import GameObjectBlueprint
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, LLMJudge

from evals.helpers import (
    CREATION_LABEL_TO_INT,
    CREATION_LABELS,
    SummaryEvaluator,
    coerce_label,
    generate_summary,
    get_run_dir,
    in_range,
    load_suite,
    parse_eval_args,
    save_report,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

# Field name -> blueprint attribute path
FIELD_TO_ATTR: dict[str, str] = {
    "mass_kg": "physics.mass_kg",
    "height_cm": "physics.height_cm",
    "surface": "physics.surface",
    "bounce": "physics.bounce",
    "gravity": "physics.gravity",
    "durability": "durability",
    "speed": "speed",
}

# Susceptibility boolean fields → (state_id, blueprint list attribute).
# Maps creation question names to membership checks on susceptible_states.
# Initial state is scored separately via _score_initial_state below — it is a
# single-pick enum in the fixture (e.g. `initial_state: burning`), not a bool.
STATE_FIELD_MAP: dict[str, tuple[int, str]] = {
    "catches_fire": (1, "susceptible_states"),
    "can_freeze": (2, "susceptible_states"),
    "gets_wet": (3, "susceptible_states"),
    "conducts_electricity": (4, "susceptible_states"),
}

_STATE_NAME_TO_ID: dict[str, int] = CREATION_LABEL_TO_INT["initial_state"]
_STATE_NAMES: dict[int, str] = {v: k for k, v in _STATE_NAME_TO_ID.items() if v != 0}


def _creation_label(field: str, value: object) -> str:
    """Return human-readable label for a creation field value."""
    labels = CREATION_LABELS.get(field)
    if labels and isinstance(value, (int, float)):
        return labels.get(int(value), str(value))
    return str(value)


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
            if field == "initial_state":
                expected_name = str(val).lower()
                expected_id = _STATE_NAME_TO_ID.get(expected_name)
                if expected_id is None:
                    continue  # unknown state name in fixture — skip rather than crash
                actual_list = bp.initial_states
                passed = len(actual_list) == 0 if expected_id == 0 else expected_id in actual_list
                actual_names = [_STATE_NAMES.get(s, str(s)) for s in actual_list] or ["none"]
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {actual_names}, expected {expected_name}",
                )
            elif field in STATE_FIELD_MAP:
                state_id, attr_name = STATE_FIELD_MAP[field]
                actual_list = getattr(bp, attr_name)
                actual_present = state_id in actual_list
                passed = actual_present == bool(val)
                state_name = _STATE_NAMES.get(state_id, str(state_id))
                actual_names = [_STATE_NAMES.get(s, str(s)) for s in actual_list]
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None
                    if passed
                    else f"{state_name} {'not ' if val else ''}in {attr_name}: {actual_names}",
                )
            elif isinstance(val, list) and len(val) == 2:
                attr_path: str = FIELD_TO_ATTR.get(field, field)
                actual_num = float(_get_nested(bp, attr_path))  # type: ignore[arg-type]
                lo = coerce_label(field, val[0])
                hi = coerce_label(field, val[1])
                passed = in_range(actual_num, lo, hi)
                actual_lbl = _creation_label(field, actual_num)
                lo_lbl = _creation_label(field, lo)
                hi_lbl = _creation_label(field, hi)
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {actual_lbl}, expected [{lo_lbl}, {hi_lbl}]",
                )
            elif isinstance(val, (bool, int)) or (
                isinstance(val, str) and field in CREATION_LABEL_TO_INT
            ):
                attr_path = FIELD_TO_ATTR.get(field, field)
                actual = _get_nested(bp, attr_path)
                expected_num = coerce_label(field, val) if isinstance(val, str) else val
                passed = actual == expected_num
                got = _creation_label(field, actual)
                exp = _creation_label(field, expected_num)
                results[field] = EvaluationReason(
                    value=passed,
                    reason=None if passed else f"got {got}, expected {exp}",
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
    args = parse_eval_args(support_judge=True)
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

    cache = await CacheStore.open(":memory:")

    async def task(inputs: str) -> GameObjectBlueprint:
        return await create_object(inputs, cache)

    dataset = build_dataset(use_judge=args.judge)
    report = await dataset.evaluate(task, name="creation", repeat=args.repeat)
    report.print(include_reasons=True)
    path = save_report(report, run_dir)
    summary = generate_summary(run_dir)
    print(f"\nResults saved to {path}")
    print(f"Summary: {summary}")

    await cache.close()


if __name__ == "__main__":
    asyncio.run(main())
