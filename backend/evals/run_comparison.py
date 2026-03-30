"""Compare saved eval results — no LLM calls.

Usage:
    # Compare two variants (finds latest result file for each):
    cd backend && uv run python -m evals.run_comparison --a baseline --b v2

    # Compare specific files:
    cd backend && uv run python -m evals.run_comparison \
        --a results/20260330_041500_baseline.json \
        --b results/20260330_042000_v2.json

    # Single variant analysis:
    cd backend && uv run python -m evals.run_comparison --a baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.distribution import print_distribution_report
from evals.io import find_latest, load_result
from evals.metrics import METRIC_NAMES
from evals.models import EvalRunResult


def load_or_find(name_or_path: str) -> EvalRunResult:
    """Load a result by file path or find the latest by variant name."""
    path = Path(name_or_path)
    if path.exists() and path.suffix == ".json":
        return load_result(path)

    # Treat as a variant name — find latest result file
    found = find_latest(name_or_path)
    if found is None:
        print(f"Error: no result file found for variant '{name_or_path}'")
        sys.exit(1)
    print(f"  Loading {found}")
    return load_result(found)


def print_wilcoxon(result_a: EvalRunResult, result_b: EvalRunResult) -> None:
    """Print Wilcoxon signed-rank test results for each metric."""
    name_a = result_a.variant
    name_b = result_b.variant

    print(
        f"\n{'Metric':<12} {name_a + ' (mean)':>12} {name_b + ' (mean)':>12} "
        f"{'Winner':>8} {'p-value':>10}"
    )
    print("-" * 56)

    # Build score lookups keyed by case name
    scores_a = {c.case: c.scores for c in result_a.cases}
    scores_b = {c.case: c.scores for c in result_b.cases}
    common = sorted(set(scores_a) & set(scores_b))

    if not common:
        print("  No common cases to compare.")
        return

    a_wins = 0
    b_wins = 0

    for metric in METRIC_NAMES:
        vals_a = [scores_a[c].get(metric, 0.0) for c in common]
        vals_b = [scores_b[c].get(metric, 0.0) for c in common]
        mean_a = sum(vals_a) / len(vals_a)
        mean_b = sum(vals_b) / len(vals_b)

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


def print_summary(result: EvalRunResult) -> None:
    """Print a quick score summary table from a saved result."""
    print(f"\n{'Case':<40} ", end="")
    for m in METRIC_NAMES:
        print(f"{m:>10}", end="")
    print(f"{'Retries':>8}")
    print("-" * (40 + 10 * len(METRIC_NAMES) + 8))

    for c in result.cases:
        print(f"{c.case:<40} ", end="")
        for m in METRIC_NAMES:
            val = c.scores.get(m, 0.0)
            print(f"{val:>10.2f}", end="")
        print(f"{c.retries:>8}")

    # Averages
    print("-" * (40 + 10 * len(METRIC_NAMES) + 8))
    print(f"{'Averages':<40} ", end="")
    for m in METRIC_NAMES:
        print(f"{result.mean_scores.get(m, 0.0):>10.3f}", end="")
    total_retries = sum(c.retries for c in result.cases)
    print(f"{total_retries:>8}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare saved eval results")
    parser.add_argument(
        "--a", required=True, help="First result: variant name or path to JSON file"
    )
    parser.add_argument(
        "--b", default=None, help="Second result: variant name or path to JSON file"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"\nLoading result A: {args.a}")
    result_a = load_or_find(args.a)
    n = result_a.dataset.total_cases
    print(f"  Variant: {result_a.variant}, {n} cases, {result_a.timestamp}")

    if args.b is None:
        # Single variant analysis
        print_summary(result_a)
        print_distribution_report(result_a)
    else:
        # Comparison mode
        print(f"\nLoading result B: {args.b}")
        result_b = load_or_find(args.b)
        print(
            f"  Variant: {result_b.variant}, {result_b.dataset.total_cases} cases, "
            f"{result_b.timestamp}"
        )

        # Validate comparable
        cases_a = set(result_a.dataset.case_names)
        cases_b = set(result_b.dataset.case_names)
        if cases_a != cases_b:
            only_a = cases_a - cases_b
            only_b = cases_b - cases_a
            if only_a:
                print(f"  Warning: {len(only_a)} cases only in A: {', '.join(sorted(only_a)[:5])}")
            if only_b:
                print(f"  Warning: {len(only_b)} cases only in B: {', '.join(sorted(only_b)[:5])}")

        # Summary tables
        print(f"\n--- {result_a.variant} ---")
        print_summary(result_a)
        print(f"\n--- {result_b.variant} ---")
        print_summary(result_b)

        # Statistical comparison
        print_wilcoxon(result_a, result_b)

        # Distribution for both
        print(f"--- Distribution: {result_a.variant} ---")
        print_distribution_report(result_a)
        print(f"\n--- Distribution: {result_b.variant} ---")
        print_distribution_report(result_b)


if __name__ == "__main__":
    main()
