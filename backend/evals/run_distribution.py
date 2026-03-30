"""Show distribution analysis for a saved eval result.

Usage:
    cd backend && uv run python -m evals.run_distribution baseline
    cd backend && uv run python -m evals.run_distribution results/20260330_045934_baseline.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.distribution import print_distribution_report
from evals.io import find_latest, load_result


def main():
    parser = argparse.ArgumentParser(description="Show distribution analysis for a saved eval result")
    parser.add_argument("result", help="Variant name or path to result JSON file")
    args = parser.parse_args()

    path = Path(args.result)
    if path.exists() and path.suffix == ".json":
        result = load_result(path)
    else:
        found = find_latest(args.result)
        if found is None:
            print(f"Error: no result file found for variant '{args.result}'")
            sys.exit(1)
        path = found
        result = load_result(found)

    print(f"\n  {path.name}")
    print(f"  Variant: {result.variant}, {result.dataset.total_cases} cases, {result.timestamp}")
    print_distribution_report(result)


if __name__ == "__main__":
    main()
