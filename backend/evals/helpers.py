"""Shared helpers for eval runners."""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from app.models.blueprint import (
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
    STATE_STRING_TO_CODE[f"remove_{_s.name.lower()}"] = _s.value + len(
        State
    )  # "remove_burning" -> 5


def parse_eval_args(*, support_judge: bool = False) -> argparse.Namespace:
    """Shared CLI argument parser for eval runners."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3, help="Repeats per case (default: 3)")
    if support_judge:
        parser.add_argument("--judge", action="store_true", help="Enable LLM judge")
    return parser.parse_args()


def get_run_dir() -> Path:
    """Return the run directory for this eval invocation.

    If EVAL_RUN_DIR env var is set (a folder name), use RESULTS_DIR / that name.
    Otherwise create a new timestamped directory.
    """
    env_dir = os.environ.get("EVAL_RUN_DIR")
    if env_dir:
        run_dir = RESULTS_DIR / env_dir
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = RESULTS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


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
    name: str,
    archetype: dict[str, Any] | None = None,
    **overrides: Any,
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
            surface=int(data.get("surface", 1)),
            bounce=int(data.get("bounce", 10)),
            gravity=int(data.get("gravity", 50)),
        ),
        durability=int(data.get("durability", 2)),
        affordance=int(data.get("affordance", 3)),
        autonomous=bool(data.get("autonomous", False)),
        speed=int(data.get("speed", 2)),
        initial_states=data.get("initial_states", []),
        susceptible_states=data.get("susceptible_states", []),
    )


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


def save_report(report: EvaluationReport, run_dir: Path) -> Path:
    """Serialize report to JSON in the given run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{report.name}.json"
    path.write_bytes(_report_adapter.dump_json(report, indent=2))
    return path


def generate_summary(run_dir: Path) -> Path:
    """Generate summary.md from all report JSONs in run_dir. Idempotent."""
    reports: list[EvaluationReport] = []
    for json_path in sorted(run_dir.glob("*.json")):
        report = _report_adapter.validate_json(json_path.read_bytes())
        reports.append(report)

    lines: list[str] = [f"# Eval Run {run_dir.name}\n"]

    if reports:
        # Overview table
        lines.append("| Report | Pass Rate | Cases |")
        lines.append("|--------|-----------|-------|")
        for report in reports:
            pass_rate = "N/A"
            for a in report.analyses:
                if isinstance(a, ScalarResult) and "pass rate" in a.title.lower():
                    pass_rate = f"{a.value}{a.unit}"
                    break
            lines.append(f"| {report.name} | {pass_rate} | {len(report.cases)} |")

        # Per-report detail
        for report in reports:
            lines.append(f"\n## {report.name}\n")
            for analysis in report.analyses:
                if isinstance(analysis, ScalarResult):
                    lines.append(f"**{analysis.title}: {analysis.value}{analysis.unit}**\n")
                elif isinstance(analysis, TableResult):
                    lines.append(f"### {analysis.title}\n")
                    lines.append("| " + " | ".join(str(c) for c in analysis.columns) + " |")
                    lines.append("|" + "|".join("---" for _ in analysis.columns) + "|")
                    lines.extend(
                        "| " + " | ".join(str(v) for v in row) + " |" for row in analysis.rows
                    )
                    lines.append("")

    summary_path = run_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path
