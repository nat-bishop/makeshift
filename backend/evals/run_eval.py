"""Creator agent eval runner — runs evals and saves results.

Usage:
    # Fast gate check (deterministic only, no LLM judges):
    cd backend && uv run python -m evals.run_eval --gate

    # Full eval run:
    cd backend && uv run python -m evals.run_eval --name my_experiment

    # Full eval + auto-compare to baseline:
    cd backend && uv run python -m evals.run_eval --name my_experiment --compare

    # Promote a run to current baseline:
    cd backend && uv run python -m evals.run_eval --promote my_experiment

    # List all saved runs:
    cd backend && uv run python -m evals.run_eval --list

    # Run a specific prompt variant:
    cd backend && uv run python -m evals.run_eval --variant compact

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

from evals.conftest import make_agent, make_split_task, make_task
from evals.dataset import EVAL_CASES, build_dataset
from evals.distribution import print_distribution_report
from evals.io import (
    RESULTS_DIR,
    list_all_runs,
    load_result,
    promote_to_baseline,
    report_to_result,
    save_comparison_report,
    save_result,
)
from evals.metrics import default_evaluators, gate_evaluators
from evals.prompts import PROMPT_VARIANTS, SPLIT_VARIANTS


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
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run each case N times for judge variance calibration (default: 1)",
    )
    parser.add_argument(
        "--gate", action="store_true",
        help="Run gate subset with deterministic metrics only (fast, no LLM judges)",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Auto-compare results against current_baseline after the run",
    )
    parser.add_argument(
        "--promote", metavar="NAME",
        help="Promote a named run to current_baseline (no eval run)",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_runs",
        help="List all saved runs with date, name, and mean scores",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # --list: show all runs and exit
    if args.list_runs:
        list_all_runs()
        return

    # --promote: promote a run to baseline and exit
    if args.promote:
        promote_to_baseline(args.promote)
        return

    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")
    logfire.instrument_pydantic_ai()

    variant = args.variant
    all_variants = {**PROMPT_VARIANTS, **{k: k for k in SPLIT_VARIANTS}}
    if variant not in all_variants and variant not in SPLIT_VARIANTS:
        available = list(PROMPT_VARIANTS.keys()) + list(SPLIT_VARIANTS.keys())
        print(f"Error: variant '{variant}' not found. Available: {available}")
        sys.exit(1)

    run_name = args.name or variant

    # Build dataset and evaluators
    if args.gate:
        from evals.gate_dataset import build_gate_dataset

        dataset = build_gate_dataset(evaluators=gate_evaluators())
        run_name = f"gate_{run_name}"
    elif args.cases:
        requested = {c.strip().lower() for c in args.cases.split(",")}
        cases = [c for c in EVAL_CASES if c.name and c.name.lower() in requested]
        if not cases:
            print(f"Error: no matching cases for '{args.cases}'")
            sys.exit(1)
        dataset = Dataset(cases=cases, evaluators=default_evaluators())
    else:
        dataset = build_dataset(evaluators=default_evaluators())

    repeat = args.repeat
    repeat_msg = f", repeat={repeat}" if repeat > 1 else ""
    mode = "gate" if args.gate else "full"
    print(
        f"\nRunning {len(dataset.cases)} eval cases ({mode}) — "
        f"variant '{variant}', name '{run_name}'{repeat_msg}..."
    )

    if variant in SPLIT_VARIANTS:
        from evals.split_models import ClassifyOutput, CreativeOutput

        classify_prompt, creative_prompt = SPLIT_VARIANTS[variant]
        classify_agent = make_agent(classify_prompt, output_type=ClassifyOutput)
        creative_agent = make_agent(creative_prompt, output_type=CreativeOutput)
        task_fn = make_split_task(classify_agent, creative_agent)
    else:
        agent = make_agent(PROMPT_VARIANTS[variant])
        task_fn = make_task(agent)

    report = await dataset.evaluate(
        task_fn, name=run_name, max_concurrency=8, repeat=repeat,
    )

    # Print pydantic-evals report (may fail on Windows legacy terminals with Unicode)
    try:
        report.print(include_input=True, include_reasons=True)
    except UnicodeEncodeError:
        print("(Report table skipped — Unicode rendering unsupported in this terminal)")

    # Convert and save
    result = report_to_result(report, variant, settings.llm_model, name=run_name)
    run_dir = save_result(result)
    print(f"\nResults saved to {run_dir}")

    # Distribution stats
    print_distribution_report(result)

    # --compare: compare against current baseline
    if args.compare:
        baseline_dir = RESULTS_DIR / "current_baseline"
        if not baseline_dir.exists() or not (baseline_dir / "result.json").exists():
            print("\nNo current_baseline found. Run with --promote <name> to set one.")
        else:
            from evals.run_comparison import print_wilcoxon

            baseline = load_result(baseline_dir)
            print(f"\n--- Comparing against baseline: {baseline.name} ---")
            print_wilcoxon(baseline, result)
            save_comparison_report(run_dir, baseline, result)
            print(f"Comparison report saved to {run_dir / 'comparison.md'}")


if __name__ == "__main__":
    asyncio.run(main())
