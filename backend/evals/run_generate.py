"""Run the creator agent on eval cases and save outputs (no scoring).

Produces the standard EvalRunResult JSON with empty scores.
Use run_score.py to score the outputs separately, or run_eval.py to do both.

Usage:
    cd backend && uv run python -m evals.run_generate
    cd backend && uv run python -m evals.run_generate --variant baseline
    cd backend && uv run python -m evals.run_generate --variant baseline --cases "fire sword,rock"
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import logfire
from app.config import settings
from pydantic_evals import Dataset

from evals.conftest import make_agent, make_task
from evals.dataset import EVAL_CASES
from evals.io import report_to_result, save_result
from evals.prompts import PROMPT_VARIANTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run creator agent on eval cases (no scoring)")
    parser.add_argument(
        "--variant", default="baseline", help="Prompt variant name (default: baseline)"
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Comma-separated case names to filter (default: all)",
    )
    return parser.parse_args()


async def main() -> None:
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")
    logfire.instrument_pydantic_ai()

    args = parse_args()

    variant = args.variant
    if variant not in PROMPT_VARIANTS:
        print(f"Error: variant '{variant}' not found. Available: {list(PROMPT_VARIANTS.keys())}")
        sys.exit(1)

    if args.cases:
        requested = {c.strip().lower() for c in args.cases.split(",")}
        cases = [c for c in EVAL_CASES if c.name.lower() in requested]
        if not cases:
            print(f"Error: no matching cases for '{args.cases}'")
            sys.exit(1)
        dataset = Dataset(cases=cases)
    else:
        dataset = Dataset(cases=list(EVAL_CASES))

    print(f"\nGenerating {len(dataset.cases)} cases with variant '{variant}' (no scoring)...")

    agent = make_agent(PROMPT_VARIANTS[variant])
    report = await dataset.evaluate(make_task(agent), name=variant, max_concurrency=8)

    report.print(include_input=True)

    result = report_to_result(report, variant, settings.llm_model)
    run_dir = save_result(result)
    print(f"\nResults saved to {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
