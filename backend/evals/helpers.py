"""Shared helpers for eval runners."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from app.cache.store import normalize_name
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.models.state import State
from pydantic import TypeAdapter
from pydantic_evals.evaluators import ReportEvaluator, ReportEvaluatorContext
from pydantic_evals.reporting import EvaluationReport, ReportAnalysis
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# State string <-> integer code mapping (built from State enum to prevent drift)
# ---------------------------------------------------------------------------

STATE_STRING_TO_CODE: dict[str, int] = {}
for _s in State:
    STATE_STRING_TO_CODE[_s.name.lower()] = _s.value  # "burning" -> 1
    STATE_STRING_TO_CODE[f"remove_{_s.name.lower()}"] = _s.value + len(State)  # "remove_burning" -> 5

def in_range(actual: float, lo: float, hi: float) -> bool:
    """Binary range check: True if lo <= actual <= hi."""
    return lo <= actual <= hi


# ---------------------------------------------------------------------------
# Unified fixture loader
# ---------------------------------------------------------------------------

_suite_cache: dict | None = None


def load_suite() -> dict:
    """Load the unified eval fixture (cached)."""
    global _suite_cache
    if _suite_cache is None:
        with open(FIXTURES_DIR / "eval_suite.yaml") as f:
            _suite_cache = yaml.safe_load(f)
    return _suite_cache


# ---------------------------------------------------------------------------
# Blueprint factory
# ---------------------------------------------------------------------------


def make_blueprint(
    name: str, archetype: dict[str, Any] | None = None, **overrides: Any,
) -> GameObjectBlueprint:
    """Build a minimal GameObjectBlueprint from archetype data.

    If archetype is None, looks it up from the suite fixture.
    Extra overrides are merged on top.
    """
    if archetype is None:
        suite = load_suite()
        archetypes = suite["archetypes"]
        key = name.lower() if name.lower() in archetypes else name
        archetype = archetypes.get(key, {})

    data = {**archetype, **overrides}

    return GameObjectBlueprint(
        id=f"eval-{name}",
        name=name,
        description=name,
        visual_description=f"a {name}",
        physics=PhysicsProperties(
            mass_kg=float(data.get("mass_kg", 1.0)),
            height_cm=int(data.get("height_cm", 30)),
            friction=int(data.get("friction", 50)),
            bounce=int(data.get("bounce", 10)),
            gravity=int(data.get("gravity", 50)),
        ),
        destructibility=Destructibility(
            armor=int(data.get("armor", 30)),
            hp=int(data.get("hp", 50)),
            indestructible=bool(data.get("indestructible", False)),
        ),
        affordance=int(data.get("affordance", 3)),
        autonomous=bool(data.get("autonomous", False)),
        has_field=bool(data.get("has_field", False)),
        field_range_cm=int(data.get("field_range_cm", 0)),
    )


# ---------------------------------------------------------------------------
# Pair orientation helper
# ---------------------------------------------------------------------------

_SIDE_FIELDS = {
    "damage_a": "damage_b",
    "damage_b": "damage_a",
    "state_a": "state_b",
    "state_b": "state_a",
}


def orient_expected(pair: list[str], expected: dict) -> dict:
    """Remap expected a/b fields to match evaluate_pair's sorted order.

    evaluate_pair() sorts A/B lexicographically by normalized name.
    Fixture pairs may list them in either order, so if the fixture's A
    sorts after B, we swap all a/b suffixed fields.
    force_b is signed and always relative to the sorted B, so negate on swap.
    """
    a, b = normalize_name(pair[0]), normalize_name(pair[1])
    if a <= b:
        return expected
    swapped: dict = {}
    for k, v in expected.items():
        new_key = _SIDE_FIELDS.get(k, k)
        if k == "force_b" and isinstance(v, list):
            # Negate and reverse the range bounds for signed force
            v = [-v[1], -v[0]]
        swapped[new_key] = v
    return swapped


# ---------------------------------------------------------------------------
# Report evaluator: per-field pass rates + overall summary
# ---------------------------------------------------------------------------


@dataclass(repr=False)
class SummaryEvaluator(ReportEvaluator):
    """Aggregate pass rates across all cases — overall + per-field breakdown."""

    def evaluate(self, ctx: ReportEvaluatorContext) -> list[ReportAnalysis]:
        field_pass: dict[str, int] = defaultdict(int)
        field_total: dict[str, int] = defaultdict(int)

        for case in ctx.report.cases:
            for name, result in case.assertions.items():
                field_total[name] += 1
                if result.value:
                    field_pass[name] += 1

        total = sum(field_total.values())
        passed = sum(field_pass.values())
        overall_pct = (passed / total * 100) if total else 0.0

        # Per-field table sorted worst-first
        rows: list[list[str | int | float | bool | None]] = []
        for field in sorted(field_total, key=lambda f: field_pass[f] / max(field_total[f], 1)):
            t = field_total[field]
            p = field_pass[field]
            pct = p / t * 100 if t else 0.0
            rows.append([field, f"{pct:.0f}%", p, t - p, t])

        analyses: list[ReportAnalysis] = [
            ScalarResult(title="Overall pass rate", value=round(overall_pct, 1), unit="%"),
        ]
        if rows:
            analyses.append(
                TableResult(
                    title="Per-field pass rates (worst first)",
                    columns=["Field", "Pass %", "Passed", "Failed", "Total"],
                    rows=rows,
                )
            )
        return analyses


# ---------------------------------------------------------------------------
# Save report to JSON
# ---------------------------------------------------------------------------

_report_adapter = TypeAdapter(EvaluationReport)


def save_report(report: EvaluationReport) -> Path:
    """Serialize report to JSON in backend/evals/results/."""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"{timestamp}_{report.name}.json"
    path.write_bytes(_report_adapter.dump_json(report, indent=2))
    return path
