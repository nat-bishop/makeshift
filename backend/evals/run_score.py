"""Score an existing results directory without re-running the creator agent.

Reads outputs from a saved EvalRunResult, runs evaluators on the
cached outputs, and saves a new fully-scored result.

Usage:
    cd backend && uv run python -m evals.run_score evals/results/20260331_053323_baseline
    cd backend && uv run python -m evals.run_score --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import logfire
from pydantic_evals import Case, Dataset

from evals.dataset import CaseMeta
from evals.distribution import print_distribution_report
from evals.io import load_result, report_to_result, save_result
from evals.metrics import default_evaluators


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a saved results directory (no agent calls)")
    parser.add_argument("results_dir", help="Path to results directory to score")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Score each case N times to measure judge variance (default: 1)",
    )
    parser.add_argument(
        "--name", default=None, help="Override the run name for the saved result"
    )
    return parser.parse_args()


async def main() -> None:
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")

    args = parse_args()
    path = Path(args.results_dir)
    if not (path / "result.json").exists():
        print(f"Error: {path}/result.json not found")
        sys.exit(1)

    existing = load_result(path)
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
                expected_substance=c.expected_substance,
                expected_element=c.expected_element,
            ),
        ))

    if not cases:
        print("Error: no scorable cases (all outputs missing)")
        sys.exit(1)

    repeat = args.repeat
    run_name = args.name or variant
    repeat_msg = f", repeat={repeat}" if repeat > 1 else ""
    print(f"Scoring {len(cases)} cases from {path.name} (variant: {variant}{repeat_msg})\n")

    async def cached_task(description: str) -> str:
        return outputs[description]

    dataset = Dataset(cases=cases, evaluators=default_evaluators())
    report = await dataset.evaluate(
        cached_task, name=run_name, max_concurrency=64, repeat=repeat,
    )

    report.print(include_input=True, include_reasons=True)

    result = report_to_result(report, variant, model, name=run_name)
    run_dir = save_result(result)
    print(f"\nScored results saved to {run_dir}")
    print_distribution_report(result)


if __name__ == "__main__":
    asyncio.run(main())
