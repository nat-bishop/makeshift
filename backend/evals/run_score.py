"""Score an existing results file without re-running the creator agent.

Reads outputs from a saved EvalRunResult JSON, runs evaluators on the
cached outputs, and saves a new fully-scored result file.

Usage:
    cd backend && uv run python -m evals.run_score evals/results/20260330_051508_split.json
    cd backend && uv run python -m evals.run_score --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import logfire
from pydantic_evals import Case, Dataset

from evals.dataset import CaseMeta
from evals.distribution import print_distribution_report
from evals.io import load_result, report_to_result, save_result
from evals.metrics import default_evaluators
from evals.models import EvalRunResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a saved results file (no agent calls)")
    parser.add_argument("results_file", help="Path to results JSON file to score")
    return parser.parse_args()


def _load_flexible(path: Path) -> EvalRunResult:
    """Load a results file, handling both EvalRunResult and raw run_split format."""
    text = path.read_text()
    try:
        return load_result(path)
    except Exception:
        pass

    # Fallback: raw format from run_split.py (has output dict, not output_raw string)
    data = json.loads(text)
    from evals.models import CaseResult, DatasetInfo, ParsedOutput

    cases = []
    for c in data["cases"]:
        output = c.get("output")
        output_raw = c.get("output_raw")
        if output and not output_raw:
            output_raw = json.dumps(output, indent=2)

        parsed = None
        if output:
            parsed = ParsedOutput(
                name=output.get("name", ""),
                tags=output.get("tags", []),
                behaviors=output.get("behaviors", []),
                size_category=output.get("size_category", "unknown"),
                visual_description=output.get("visual_description", ""),
            )

        cases.append(CaseResult(
            case=c["case"],
            inputs=c["inputs"],
            category=c.get("category", "unknown"),
            expected_tags=c.get("expected_tags", []),
            output_raw=output_raw,
            output=parsed,
            error=c.get("error"),
            scores=c.get("scores", {}),
            reasons=c.get("reasons", {}),
            elapsed=c.get("elapsed", 0.0),
            retries=c.get("retries", 0),
        ))

    ds = data.get("dataset", {})
    return EvalRunResult(
        variant=data.get("variant", "unknown"),
        timestamp=data.get("timestamp", "2000-01-01T00:00:00Z"),
        model=data.get("model", "unknown"),
        judge_model="",
        dataset=DatasetInfo(
            total_cases=ds.get("total_cases", len(cases)),
            categories=ds.get("categories", {}),
            case_names=ds.get("case_names", [c.case for c in cases]),
        ),
        cases=cases,
        mean_scores={},
        retry_stats={},
    )


async def main() -> None:
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")

    args = parse_args()
    path = Path(args.results_file)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    existing = _load_flexible(path)
    variant = existing.variant
    model = existing.model

    # Build output lookup and pydantic-evals cases
    outputs: dict[str, str] = {}
    cases: list[Case[str, str, CaseMeta]] = []
    for c in existing.cases:
        if not c.output_raw:
            continue
        outputs[c.inputs] = c.output_raw
        cases.append(Case(
            name=c.case,
            inputs=c.inputs,
            metadata=CaseMeta(
                category=c.category,
                expected_tags=c.expected_tags,
            ),
        ))

    if not cases:
        print("Error: no scorable cases (all outputs missing)")
        sys.exit(1)

    print(f"Scoring {len(cases)} cases from {path.name} (variant: {variant})\n")

    async def cached_task(description: str) -> str:
        return outputs[description]

    dataset = Dataset(cases=cases, evaluators=default_evaluators())
    report = await dataset.evaluate(cached_task, name=variant, max_concurrency=8)

    report.print(include_input=True, include_reasons=True)

    result = report_to_result(report, variant, model)
    scored_path = save_result(result)
    print(f"\nScored results saved to {scored_path}")

    print_distribution_report(result)


if __name__ == "__main__":
    asyncio.run(main())
