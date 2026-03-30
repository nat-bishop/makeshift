"""Creator agent prompt comparison runner.

Usage:
    # Compare two prompt variants:
    uv run python -m evals.run_comparison --a baseline --b v2

    # Score a single variant:
    uv run python -m evals.run_comparison --a baseline --single

    # Filter to specific cases:
    uv run python -m evals.run_comparison --a baseline --b v2 --cases "fire sword,rubber duck"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from evals.conftest import make_agent, make_task
from evals.dataset import EVAL_CASES, CaseMeta, CreatorCase
from evals.distribution import print_distribution_report
from evals.metrics import METRIC_NAMES, default_evaluators
from evals.prompts import PROMPT_VARIANTS

RESULTS_DIR = Path(__file__).parent / "results"


def get_score(report_case, metric_name: str) -> float:
    """Extract a numeric score from a report case."""
    result = report_case.scores.get(metric_name)
    return result.value if result else 0.0


async def evaluate_variant(
    variant_name: str,
    prompt: str,
    cases: list[CreatorCase],
) -> EvaluationReport[str, str, CaseMeta]:
    """Run all cases through a prompt variant and score with all evaluators."""
    agent = make_agent(prompt)
    dataset = Dataset(cases=cases, evaluators=default_evaluators())
    return await dataset.evaluate(make_task(agent), name=variant_name, max_concurrency=1)


def print_wilcoxon(
    report_a: EvaluationReport,
    report_b: EvaluationReport,
) -> None:
    """Print Wilcoxon signed-rank test results for each metric."""
    name_a = report_a.name or "A"
    name_b = report_b.name or "B"

    print(
        f"\n{'Metric':<12} {name_a + ' (mean)':>12} {name_b + ' (mean)':>12} "
        f"{'Winner':>8} {'p-value':>10}"
    )
    print("-" * 56)

    a_wins = 0
    b_wins = 0

    for metric in METRIC_NAMES:
        vals_a = [get_score(c, metric) for c in report_a.cases]
        vals_b = [get_score(c, metric) for c in report_b.cases]
        mean_a = sum(vals_a) / len(vals_a) if vals_a else 0
        mean_b = sum(vals_b) / len(vals_b) if vals_b else 0

        # Wilcoxon signed-rank test (paired)
        p_str = "  —"
        try:
            from scipy.stats import wilcoxon

            diffs = [a - b for a, b in zip(vals_a, vals_b, strict=True)]
            if any(d != 0 for d in diffs):
                _, p = wilcoxon(diffs)
                p_str = f"{p:.3f}{'*' if p < 0.05 else ' '}"
            else:
                p_str = "  1.000 "
        except ImportError:
            p_str = "  (no scipy)"

        if mean_a > mean_b:
            winner = name_a
            a_wins += 1
        elif mean_b > mean_a:
            winner = name_b
            b_wins += 1
        else:
            winner = "tie"

        print(f"{metric:<12} {mean_a:>12.3f} {mean_b:>12.3f} {winner:>8} {p_str:>10}")

    overall = name_a if a_wins > b_wins else name_b if b_wins > a_wins else "tie"
    print(f"\nOverall winner: {overall} ({max(a_wins, b_wins)}/{len(METRIC_NAMES)} metrics)")
    print()


def save_results(
    report_a: EvaluationReport,
    report_b: EvaluationReport | None = None,
) -> None:
    """Save raw results as timestamped JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    names = report_a.name or "unknown"
    if report_b:
        names += f"_vs_{report_b.name or 'unknown'}"
    path = RESULTS_DIR / f"{ts}_{names}.json"

    data = []
    for report in [report_a] + ([report_b] if report_b else []):
        for rc in report.cases:
            data.append({
                "case": rc.name,
                "variant": report.name,
                "output": rc.output,
                "scores": {k: v.value for k, v in rc.scores.items()},
                "reasons": {k: v.reason for k, v in rc.scores.items()},
                "elapsed": rc.task_duration,
            })

    path.write_text(json.dumps(data, indent=2))
    print(f"Results saved to {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Creator agent prompt comparison")
    parser.add_argument("--a", required=True, help="First prompt variant name")
    parser.add_argument("--b", default=None, help="Second prompt variant name (omit for --single)")
    parser.add_argument("--single", action="store_true", help="Score a single variant only")
    parser.add_argument(
        "--cases",
        default=None,
        help="Comma-separated case descriptions to filter (default: all)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Validate variant names
    variant_a = args.a
    if variant_a not in PROMPT_VARIANTS:
        print(f"Error: variant '{variant_a}' not found. Available: {list(PROMPT_VARIANTS.keys())}")
        sys.exit(1)

    if not args.single and not args.b:
        print("Error: provide --b <variant> or use --single")
        sys.exit(1)

    if args.b and args.b not in PROMPT_VARIANTS:
        print(f"Error: variant '{args.b}' not found. Available: {list(PROMPT_VARIANTS.keys())}")
        sys.exit(1)

    # Filter cases
    cases = list(EVAL_CASES)
    if args.cases:
        requested = {c.strip().lower() for c in args.cases.split(",")}
        cases = [c for c in cases if c.name.lower() in requested]
        if not cases:
            print(f"Error: no matching cases for '{args.cases}'")
            sys.exit(1)

    print(f"\nRunning {len(cases)} eval cases...")

    # Run variant A
    print(f"\n--- Variant: {variant_a} ---")
    report_a = await evaluate_variant(variant_a, PROMPT_VARIANTS[variant_a], cases)

    if args.single:
        report_a.print(include_input=True, include_reasons=True)
        print_distribution_report(report_a)
        save_results(report_a)
    else:
        # Comparison mode
        variant_b = args.b
        print(f"\n--- Variant: {variant_b} ---")
        report_b = await evaluate_variant(variant_b, PROMPT_VARIANTS[variant_b], cases)

        # Built-in diff table
        report_b.print(baseline=report_a, include_input=True)

        # Statistical comparison
        print_wilcoxon(report_a, report_b)

        # Distribution for both variants
        print(f"--- Distribution: {variant_a} ---")
        print_distribution_report(report_a)
        print(f"--- Distribution: {variant_b} ---")
        print_distribution_report(report_b)

        save_results(report_a, report_b)


if __name__ == "__main__":
    asyncio.run(main())
