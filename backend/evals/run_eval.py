"""Creator agent eval runner — runs evals and saves results.

Usage:
    # Run all cases (default variant, name defaults to variant):
    cd backend && uv run python -m evals.run_eval

    # Name an experiment (uses baseline prompt, labels the result):
    cd backend && uv run python -m evals.run_eval --name added_hostile_remove_damage

    # Run a specific prompt variant:
    cd backend && uv run python -m evals.run_eval --variant v2

    # Both (custom prompt + custom name):
    cd backend && uv run python -m evals.run_eval --variant v2 --name v2_after_cleanup

    # Filter to specific cases:
    cd backend && uv run python -m evals.run_eval --cases "fire sword,rock"
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import logfire
from app.config import settings
from pydantic_evals import Dataset

from evals.conftest import make_agent, make_task
from evals.dataset import EVAL_CASES, build_dataset
from evals.distribution import print_distribution_report
from evals.io import report_to_result, save_result
from evals.metrics import default_evaluators
from evals.prompts import PROMPT_VARIANTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run creator agent evals and save results")
    parser.add_argument(
        "--variant", default="baseline", help="Prompt variant name (default: baseline)"
    )
    parser.add_argument(
        "--name", default=None, help="Experiment name for the result file (default: variant name)"
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Comma-separated case names to filter (default: all)",
    )
    return parser.parse_args()


async def main():
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")
    logfire.instrument_pydantic_ai()

    args = parse_args()

    variant = args.variant
    if variant not in PROMPT_VARIANTS:
        print(f"Error: variant '{variant}' not found. Available: {list(PROMPT_VARIANTS.keys())}")
        sys.exit(1)

    run_name = args.name or variant

    # Filter cases
    if args.cases:
        requested = {c.strip().lower() for c in args.cases.split(",")}
        cases = [c for c in EVAL_CASES if c.name.lower() in requested]
        if not cases:
            print(f"Error: no matching cases for '{args.cases}'")
            sys.exit(1)
        dataset = Dataset(cases=cases, evaluators=default_evaluators())
    else:
        dataset = build_dataset(evaluators=default_evaluators())

    print(f"\nRunning {len(dataset.cases)} eval cases — variant '{variant}', name '{run_name}'...")

    agent = make_agent(PROMPT_VARIANTS[variant])
    report = await dataset.evaluate(make_task(agent), name=run_name, max_concurrency=8)

    # Print pydantic-evals report
    report.print(include_input=True, include_reasons=True)

    # Convert and save
    result = report_to_result(report, variant, settings.llm_model, name=run_name)
    run_dir = save_result(result)
    print(f"\nResults saved to {run_dir}")

    # Distribution stats
    print_distribution_report(result)


if __name__ == "__main__":
    asyncio.run(main())
