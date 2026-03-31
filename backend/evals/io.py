"""Save, load, and convert eval results.

Bridges pydantic-evals EvaluationReport to our persistent EvalRunResult format.
"""

from __future__ import annotations

import contextlib
import json
import re
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


def _resolve_behaviors(tags: list[str], signature: str | None) -> list[str]:
    """Resolve tag-implied + signature behaviors into display strings."""
    from app.models.behaviors import BehaviorParseError, expand_behavior_spec, parse_behavior_string
    from app.models.tag_behaviors import resolve_implied_behaviors
    from app.models.tags import Tag

    parsed_tags: list[Tag] = []
    for t in tags:
        try:
            parsed_tags.append(Tag(t))
        except (ValueError, KeyError):
            continue

    explicit = None
    if signature:
        with contextlib.suppress(BehaviorParseError, ValueError):
            explicit = expand_behavior_spec(parse_behavior_string(signature))

    resolved = resolve_implied_behaviors(parsed_tags, explicit)

    # Format back to readable strings
    lines: list[str] = []
    for b in resolved:
        parts = [b.trigger.value, b.action.value]
        if b.target.value != "SELF":
            parts.append(b.target.value)
        line = " -> ".join(parts)
        if b.tags_to_apply:
            # Already encoded in action via parametric syntax
            pass
        if b.trigger_tag:
            parts[0] = f"{b.trigger.value}({b.trigger_tag.value})"
            line = " -> ".join(parts)
        lines.append(line)
    return lines


def _parse_output(raw: str) -> ParsedOutput | None:
    """Parse a CreatorOutputSpec JSON string into structured fields."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    vd = data.get("visual_descriptor", {})
    tags = data.get("tags", [])
    signature = data.get("signature")
    return ParsedOutput(
        name=data.get("name", ""),
        tags=tags,
        signature=signature,
        resolved_behaviors=_resolve_behaviors(tags, signature),
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
    path.write_text(result.model_dump_json(indent=2))

    # Also save markdown report
    from evals.markdown_report import generate_markdown_report

    md_path = run_dir / "report.md"
    md_path.write_text(generate_markdown_report(result), encoding="utf-8")

    return run_dir


def load_result(path: Path) -> EvalRunResult:
    """Load an EvalRunResult from a run directory."""
    return EvalRunResult.model_validate_json((path / "result.json").read_text())


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
