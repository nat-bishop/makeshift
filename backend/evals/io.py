"""Save, load, and convert eval results.

Bridges pydantic-evals EvaluationReport to our persistent EvalRunResult format.
Also provides baseline management and run listing for the eval workflow.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic_evals.reporting import EvaluationReport

from evals.conftest import JUDGE_MODEL
from evals.dataset import CaseMeta
from evals.models import CaseResult, DatasetInfo, EvalRunResult, ParsedOutput

_RETRY_RE = re.compile(r"Exceeded maximum retries \((\d+)\)")

RESULTS_DIR = Path(__file__).parent / "results"


def _extract_failure_retry_info(
    error_message: str, error_stacktrace: str
) -> tuple[int, list[str]]:
    """Extract retry count and errors from a failed case.

    When pydantic-ai exhausts retries, the task function throws before
    set_eval_attribute() records retry info. We recover what we can
    from the error message and the chained exception in the stacktrace.
    """
    m = _RETRY_RE.search(error_message)
    if not m:
        return 0, []

    retries = int(m.group(1))

    # Extract the chained cause — look for the last ModelRetry or ValidationError
    retry_errors: list[str] = []
    for line in reversed(error_stacktrace.strip().splitlines()):
        line = line.strip()
        if line.startswith("pydantic_ai.exceptions.ModelRetry:"):
            retry_errors.append(line.split(":", 1)[1].strip())
            break
        if "ValidationError:" in line:
            retry_errors.append(line)
            break

    return retries, retry_errors


def _format_behaviors(behaviors: list[dict]) -> list[str]:
    """Format behavior dicts into display strings."""
    lines: list[str] = []
    for b in behaviors:
        verb = b.get("verb", "unknown")
        target_tag = b.get("target_tag", "")
        desc = b.get("target_description", b.get("target", ""))
        tag_str = f" [{target_tag}]" if target_tag else ""
        lines.append(f"{verb}{tag_str} ->{desc}")
    return lines


def _parse_output(raw: str) -> ParsedOutput | None:
    """Parse a V2 CreatorOutput JSON string into structured fields."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    vd = data.get("visual_descriptor", {})
    tags = data.get("tags", [])
    behaviors = data.get("behaviors", [])
    categories = data.get("categories", [])
    return ParsedOutput(
        name=data.get("name", ""),
        tags=tags,
        categories=categories,
        substance=data.get("substance"),
        element=data.get("element"),
        resolved_behaviors=_format_behaviors(behaviors),
        size_category=vd.get("size_category", "unknown") if isinstance(vd, dict) else "unknown",
        visual_description=(
            vd.get("visual_description", "") if isinstance(vd, dict) else ""
        ),
    )


def report_to_result(
    report: EvaluationReport[str, str, CaseMeta],
    variant: str,
    model: str,
    name: str | None = None,
) -> EvalRunResult:
    """Convert a pydantic-evals EvaluationReport to our EvalRunResult schema."""
    cases: list[CaseResult] = []

    for rc in report.cases:
        retries = rc.attributes.get("retries", 0)
        retry_errors = rc.attributes.get("retry_errors", [])
        meta = rc.metadata
        cases.append(CaseResult(
            case=rc.name,
            inputs=rc.inputs,
            category=meta.category if meta else "unknown",
            expected_tags=list(meta.expected_tags) if meta else [],
            expected_categories=list(meta.expected_categories) if meta else [],
            expected_substance=meta.expected_substance if meta else None,
            expected_element=meta.expected_element if meta else None,
            output_raw=rc.output,
            output=_parse_output(rc.output) if rc.output else None,
            error=None,
            scores={k: v.value for k, v in rc.scores.items()},
            reasons={k: v.reason or "" for k, v in rc.scores.items()},
            elapsed=rc.task_duration,
            retries=int(retries),
            retry_errors=list(retry_errors),
            trace_id=rc.trace_id,
            span_id=rc.span_id,
        ))

    for fc in report.failures:
        meta = fc.metadata
        retries, retry_errors = _extract_failure_retry_info(
            fc.error_message, fc.error_stacktrace
        )
        cases.append(CaseResult(
            case=fc.name,
            inputs=fc.inputs,
            category=meta.category if meta else "unknown",
            expected_tags=list(meta.expected_tags) if meta else [],
            expected_categories=list(meta.expected_categories) if meta else [],
            expected_substance=meta.expected_substance if meta else None,
            expected_element=meta.expected_element if meta else None,
            output_raw=None,
            output=None,
            error=fc.error_message,
            scores={},
            reasons={},
            elapsed=0.0,
            retries=retries,
            retry_errors=retry_errors,
            trace_id=fc.trace_id,
            span_id=fc.span_id,
        ))

    # Dataset info
    cat_counts = Counter(c.category for c in cases)
    dataset_info = DatasetInfo(
        total_cases=len(cases),
        categories=dict(cat_counts),
        case_names=[c.case for c in cases],
    )

    # Aggregate scores
    score_keys: set[str] = set()
    for c in cases:
        score_keys.update(c.scores.keys())
    mean_scores: dict[str, float] = {}
    for k in sorted(score_keys):
        vals = [c.scores[k] for c in cases if k in c.scores]
        mean_scores[k] = sum(vals) / len(vals) if vals else 0.0

    # Retry stats
    all_retries = [c.retries for c in cases]
    total_retries = sum(all_retries)
    first_try = sum(1 for r in all_retries if r == 0)
    retry_stats: dict[str, float | int] = {
        "total": total_retries,
        "mean": round(total_retries / len(all_retries), 2) if all_retries else 0.0,
        "max": max(all_retries) if all_retries else 0,
        "first_try_pct": round(first_try / len(all_retries) * 100, 1) if all_retries else 0.0,
    }

    return EvalRunResult(
        name=name or variant,
        variant=variant,
        timestamp=datetime.now(UTC),
        model=model,
        judge_model=JUDGE_MODEL,
        dataset=dataset_info,
        cases=cases,
        mean_scores=mean_scores,
        retry_stats=retry_stats,
    )


def _run_dir(result: EvalRunResult) -> Path:
    """Get the per-run directory for a result: results/{timestamp}_{name}/."""
    ts = result.timestamp.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"{ts}_{result.name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_result(result: EvalRunResult) -> Path:
    """Save an EvalRunResult as JSON inside a per-run directory."""
    run_dir = _run_dir(result)
    path = run_dir / "result.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    # Also save markdown report
    from evals.markdown_report import generate_markdown_report

    md_path = run_dir / "report.md"
    md_path.write_text(generate_markdown_report(result), encoding="utf-8")

    return run_dir


def load_result(path: Path) -> EvalRunResult:
    """Load an EvalRunResult from a run directory."""
    return EvalRunResult.model_validate_json((path / "result.json").read_text(encoding="utf-8"))


def find_latest(name: str | None = None) -> Path | None:
    """Find the most recent result directory, optionally filtered by run name."""
    if not RESULTS_DIR.exists():
        return None

    dirs = sorted(
        [d for d in RESULTS_DIR.iterdir() if d.is_dir() and (d / "result.json").exists()],
        key=lambda d: d.name,
        reverse=True,
    )
    for d in dirs:
        if name is None or d.name.endswith(f"_{name}"):
            return d
    return None


def promote_to_baseline(name_or_path: str) -> None:
    """Copy a result to results/current_baseline/."""
    path = Path(name_or_path)
    if path.is_dir() and (path / "result.json").exists():
        source = path
    else:
        found = find_latest(name_or_path)
        if found is None:
            print(f"Error: no result found for '{name_or_path}'")  # noqa: T201
            return
        source = found

    baseline_dir = RESULTS_DIR / "current_baseline"
    if baseline_dir.exists():
        shutil.rmtree(baseline_dir)
    shutil.copytree(source, baseline_dir)

    result = load_result(baseline_dir)
    print(f"Promoted {source.name} ->current_baseline ({result.name}, {result.timestamp:%Y-%m-%d})")


def list_all_runs() -> None:
    """Print all saved runs with date, name, and key mean scores."""
    if not RESULTS_DIR.exists():
        print("No results directory found.")
        return

    dirs = sorted(
        [
            d for d in RESULTS_DIR.iterdir()
            if d.is_dir() and d.name != "current_baseline" and (d / "result.json").exists()
        ],
        key=lambda d: d.name,
    )

    if not dirs:
        print("No saved runs found.")
        return

    # Check for current baseline
    baseline_dir = RESULTS_DIR / "current_baseline"
    if baseline_dir.exists() and (baseline_dir / "result.json").exists():
        bl = load_result(baseline_dir)
        print(f"Current baseline: {bl.name} ({bl.timestamp:%Y-%m-%d})")
        print()

    key_metrics = ["Validity", "Faithfulness", "Delight", "Visual Clarity"]
    header = f"{'Date':<12} {'Name':<25} {'Cases':>5}"
    for m in key_metrics:
        header += f"  {m:>10}"
    print(header)
    print("-" * len(header))

    for d in dirs:
        try:
            result = load_result(d)
        except Exception:
            continue
        line = f"{result.timestamp:%Y-%m-%d}   {result.name:<25} {result.dataset.total_cases:>5}"
        for m in key_metrics:
            val = result.mean_scores.get(m)
            line += f"  {val:>10.2f}" if val is not None else f"  {'—':>10}"
        print(line)

    print()


def save_comparison_report(
    run_dir: Path, baseline: EvalRunResult, result: EvalRunResult
) -> None:
    """Save a comparison report as comparison.md in the run directory."""
    from evals.metrics import METRIC_NAMES

    lines = [
        f"# Comparison: {result.name} vs baseline ({baseline.name})",
        "",
        f"**Experiment:** {result.name} ({result.timestamp:%Y-%m-%d %H:%M})",
        f"**Baseline:** {baseline.name} ({baseline.timestamp:%Y-%m-%d %H:%M})",
        "",
        "## Metric comparison",
        "",
        f"| {'Metric':<20} | {'Baseline':>10} | {'Experiment':>10} "
        f"| {'Delta':>8} | {'Winner':>12} |",
        f"|{'-' * 22}|{'-' * 12}|{'-' * 12}|{'-' * 10}|{'-' * 14}|",
    ]

    scores_a = {c.case: c.scores for c in baseline.cases}
    scores_b = {c.case: c.scores for c in result.cases}
    common = sorted(set(scores_a) & set(scores_b))

    a_wins = 0
    b_wins = 0

    for metric in METRIC_NAMES:
        vals_a = [scores_a[c].get(metric, 0.0) for c in common]
        vals_b = [scores_b[c].get(metric, 0.0) for c in common]
        mean_a = sum(vals_a) / len(vals_a) if vals_a else 0.0
        mean_b = sum(vals_b) / len(vals_b) if vals_b else 0.0
        delta = mean_b - mean_a

        p_str = ""
        try:
            from scipy.stats import wilcoxon  # type: ignore[import-untyped]

            diffs = [a - b for a, b in zip(vals_a, vals_b, strict=True)]
            if any(d != 0 for d in diffs):
                _, p = wilcoxon(diffs)
                p_str = f" (p={p:.3f}{'*' if p < 0.05 else ''})"
        except ImportError:
            pass

        if mean_b > mean_a:
            winner = result.name
            b_wins += 1
        elif mean_a > mean_b:
            winner = baseline.name
            a_wins += 1
        else:
            winner = "tie"

        lines.append(
            f"| {metric:<20} | {mean_a:>10.3f} | {mean_b:>10.3f} | "
            f"{delta:>+8.3f} | {winner:>12} |"
        )

    overall = result.name if b_wins > a_wins else baseline.name if a_wins > b_wins else "tie"
    lines.extend([
        "",
        f"**Overall winner:** {overall} "
        f"({max(a_wins, b_wins)}/{len(METRIC_NAMES)} metrics)",
    ])

    (run_dir / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
