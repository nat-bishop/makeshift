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


def _extract_category(field_name: str) -> str:
    """Extract the category (field type) from an assertion name.

    Behavior assertions: 'zombie_vs_person.action' -> 'action'
    Creation assertions: 'mass_kg', 'initially_burning' -> as-is
    Screening assertions: 'includes_wood', 'excludes_rock' -> 'includes' / 'excludes'
    """
    if "." in field_name:
        return field_name.rsplit(".", 1)[1]
    if field_name.startswith("includes_"):
        return "includes"
    if field_name.startswith("excludes_"):
        return "excludes"
    return field_name


def _bar(pct: float, width: int = 20) -> str:
    """Render a text bar chart segment."""
    filled = round(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


@dataclass(repr=False)
class SummaryEvaluator(ReportEvaluator):
    """Aggregate pass rates — overall, per-category, and per-field breakdown."""

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

        # --- Category-level aggregation ---
        cat_pass: dict[str, int] = defaultdict(int)
        cat_total: dict[str, int] = defaultdict(int)
        for field in field_total:
            cat = _extract_category(field)
            cat_pass[cat] += field_pass[field]
            cat_total[cat] += field_total[field]

        cat_rows: list[list[str | int | float | bool | None]] = []
        for cat in sorted(cat_total, key=lambda c: cat_pass[c] / max(cat_total[c], 1)):
            t = cat_total[cat]
            p = cat_pass[cat]
            pct = p / t * 100 if t else 0.0
            cat_rows.append([cat, f"{pct:.0f}%", _bar(pct), p, t - p, t])

        # --- Per-field (only failures) ---
        fail_rows: list[list[str | int | float | bool | None]] = []
        for field in sorted(field_total, key=lambda f: field_pass[f] / max(field_total[f], 1)):
            t = field_total[field]
            p = field_pass[field]
            if p < t:
                pct = p / t * 100 if t else 0.0
                fail_rows.append([field, f"{pct:.0f}%", p, t - p, t])

        analyses: list[ReportAnalysis] = [
            ScalarResult(title="Overall pass rate", value=round(overall_pct, 1), unit="%"),
        ]
        if cat_rows:
            analyses.append(
                TableResult(
                    title="By category (worst first)",
                    columns=["Category", "Pass %", "Bar", "Passed", "Failed", "Total"],
                    rows=cat_rows,
                )
            )
        if fail_rows:
            analyses.append(
                TableResult(
                    title="Failing fields (worst first)",
                    columns=["Field", "Pass %", "Passed", "Failed", "Total"],
                    rows=fail_rows,
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


def _report_stats(report: EvaluationReport) -> tuple[int, int, int]:
    """Return (unique_subjects, repetitions, total_assertions) for a report."""
    source_names = {c.source_case_name or c.name for c in report.cases}
    unique = len(source_names)
    reps = len(report.cases) // unique if unique else 0
    total_assertions = sum(len(c.assertions) for c in report.cases)
    return unique, reps, total_assertions


def _collect_failures(report: EvaluationReport) -> list[tuple[str, str, int, int, str]]:
    """Collect failing assertions, deduplicated by (source_case, assertion_name).

    Returns list of (source_case, assertion_name, fail_count, total_reps, reason)
    sorted by source_case then assertion_name.
    """
    # Group by (source_case, assertion_name)
    fail_counts: dict[tuple[str, str], int] = defaultdict(int)
    rep_counts: dict[tuple[str, str], int] = defaultdict(int)
    reasons: dict[tuple[str, str], str] = {}

    for case in report.cases:
        source = case.source_case_name or case.name
        for aname, result in case.assertions.items():
            key = (source, aname)
            rep_counts[key] += 1
            if not result.value:
                fail_counts[key] += 1
                if key not in reasons and result.reason:
                    reasons[key] = result.reason

    rows: list[tuple[str, str, int, int, str]] = []
    for key in sorted(fail_counts):
        source, aname = key
        rows.append((source, aname, fail_counts[key], rep_counts[key], reasons.get(key, "")))
    return rows


def generate_summary(run_dir: Path) -> Path:
    """Generate summary.md from all report JSONs in run_dir. Idempotent."""
    reports: list[EvaluationReport] = []
    for json_path in sorted(run_dir.glob("*.json")):
        report = _report_adapter.validate_json(json_path.read_bytes())
        reports.append(report)

    lines: list[str] = [f"# Eval Run {run_dir.name}\n"]

    if reports:
        # Overview table
        lines.append("| Report | Pass Rate | Subjects | Reps | Cases | Assertions |")
        lines.append("|--------|-----------|----------|------|-------|------------|")
        for report in reports:
            pass_rate = "N/A"
            for a in report.analyses:
                if isinstance(a, ScalarResult) and "pass rate" in a.title.lower():
                    pass_rate = f"{a.value}{a.unit}"
                    break
            unique, reps, total_assertions = _report_stats(report)
            lines.append(
                f"| {report.name} | {pass_rate} | {unique} | {reps} "
                f"| {len(report.cases)} | {total_assertions} |"
            )

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

            # Failures section
            failures = _collect_failures(report)
            if failures:
                lines.append("### Failures\n")
                lines.append("| Subject | Assertion | Failed | Reason |")
                lines.append("|---------|-----------|--------|--------|")
                for source, aname, fails, reps, reason in failures:
                    lines.append(f"| {source} | {aname} | {fails}/{reps} | {reason} |")
                lines.append("")

    summary_path = run_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path
