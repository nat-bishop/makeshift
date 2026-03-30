"""Save, load, and convert eval results.

Bridges pydantic-evals EvaluationReport to our persistent EvalRunResult format.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic_evals.reporting import EvaluationReport

from evals.conftest import JUDGE_MODEL
from evals.dataset import CaseMeta
from evals.models import CaseResult, DatasetInfo, EvalRunResult, ParsedOutput

RESULTS_DIR = Path(__file__).parent / "results"


def _parse_output(raw: str) -> ParsedOutput | None:
    """Parse a CreatorOutputSpec JSON string into structured fields."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    vd = data.get("visual_descriptor", {})
    return ParsedOutput(
        name=data.get("name", ""),
        tags=data.get("tags", []),
        behaviors=data.get("behaviors", []),
        size_category=vd.get("size_category", "unknown") if isinstance(vd, dict) else "unknown",
        visual_description=(
            vd.get("visual_description", "") if isinstance(vd, dict) else ""
        ),
    )


def report_to_result(
    report: EvaluationReport[str, str, CaseMeta],
    variant: str,
    model: str,
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
        cases.append(CaseResult(
            case=fc.name,
            inputs=fc.inputs,
            category=meta.category if meta else "unknown",
            expected_tags=list(meta.expected_tags) if meta else [],
            output_raw=None,
            output=None,
            error=fc.error_message,
            scores={},
            reasons={},
            elapsed=0.0,
            retries=0,
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
        variant=variant,
        timestamp=datetime.now(UTC),
        model=model,
        judge_model=JUDGE_MODEL,
        dataset=dataset_info,
        cases=cases,
        mean_scores=mean_scores,
        retry_stats=retry_stats,
    )


def save_result(result: EvalRunResult) -> Path:
    """Save an EvalRunResult as timestamped JSON and return the path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = result.timestamp.strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"{ts}_{result.variant}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def load_result(path: Path) -> EvalRunResult:
    """Load an EvalRunResult from a JSON file."""
    return EvalRunResult.model_validate_json(path.read_text())


def find_latest(variant: str | None = None) -> Path | None:
    """Find the most recent result file, optionally filtered by variant name."""
    if not RESULTS_DIR.exists():
        return None
    files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    for f in files:
        if variant is None or f.stem.endswith(f"_{variant}"):
            return f
    return None
