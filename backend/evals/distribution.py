"""Distribution analysis for creator agent eval outputs.

Aggregates tag, behavior, and size frequencies across all cases
in a saved EvalRunResult to show variety and output patterns.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.models.behaviors import BehaviorParseError, parse_behavior_string
from app.models.tags import LLM_VISIBLE_TAGS

from evals.models import EvalRunResult

ALL_TAGS = sorted(t.value for t in LLM_VISIBLE_TAGS)


def print_distribution_report(result: EvalRunResult) -> None:
    """Print aggregate distribution stats from a saved eval result."""
    tag_counts: Counter[str] = Counter()
    trigger_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    behavior_count_dist: Counter[int] = Counter()
    total = 0

    for case in result.cases:
        if case.output is None:
            continue
        total += 1
        out = case.output

        # Tags
        for tag in out.tags:
            tag_counts[tag] += 1

        # Size
        size_counts[out.size_category] += 1

        # Signature
        has_sig = 1 if out.signature else 0
        behavior_count_dist[has_sig] += 1
        if out.signature:
            try:
                spec = parse_behavior_string(str(out.signature))
                trigger_counts[spec.trigger.value] += 1
                action_counts[spec.action.value] += 1
                target_counts[spec.target.value] += 1
            except (BehaviorParseError, ValueError):
                pass

    if total == 0:
        print("\n  No parseable outputs for distribution analysis.\n")
        return

    print(f"\n{'=' * 60}")
    print(f"  Distribution Analysis ({total} objects)")
    print(f"{'=' * 60}")

    # Tag frequency (all tags, including zeros)
    print("\n  Tag Frequency:")
    for tag in ALL_TAGS:
        tag_counts.setdefault(tag, 0)
    for tag, count in tag_counts.most_common():
        pct = count / total * 100
        bar = "#" * int(pct / 2)
        print(f"    {tag:<16} {count:>3}/{total}  ({pct:4.0f}%)  {bar}")

    # Size distribution
    print("\n  Size Distribution:")
    for size, count in size_counts.most_common():
        pct = count / total * 100
        print(f"    {size:<10} {count:>3}/{total}  ({pct:4.0f}%)")

    # Signature distribution
    print("\n  Signature Behavior:")
    with_sig = behavior_count_dist.get(1, 0)
    without_sig = behavior_count_dist.get(0, 0)
    print(f"    with signature:    {with_sig:>3}/{total}  ({with_sig / total * 100:4.0f}%)")
    print(f"    without signature: {without_sig:>3}/{total}  ({without_sig / total * 100:4.0f}%)")

    # Trigger distribution
    if trigger_counts:
        print("\n  Trigger Types:")
        for trigger, count in trigger_counts.most_common():
            print(f"    {trigger:<20} {count:>3}")

    # Action distribution
    if action_counts:
        print("\n  Action Types:")
        for action, count in action_counts.most_common():
            print(f"    {action:<20} {count:>3}")

    # Target distribution
    if target_counts:
        print("\n  Target Types:")
        for target, count in target_counts.most_common():
            print(f"    {target:<20} {count:>3}")

    # Retry stats
    all_retries = [c.retries for c in result.cases]
    total_retries = sum(all_retries)
    first_try = sum(1 for r in all_retries if r == 0)
    print("\n  Retry Stats:")
    pct = first_try / len(all_retries) * 100
    print(f"    First-try success: {first_try}/{len(all_retries)}  ({pct:.0f}%)")
    print(f"    Avg retries:       {total_retries / len(all_retries):.2f}")
    if total_retries > 0:
        print(f"    Max retries:       {max(all_retries)}")

    # Retry reasons
    reason_counts: Counter[str] = Counter()
    for case in result.cases:
        for err in case.retry_errors:
            truncated = err[:60] + "..." if len(err) > 60 else err
            reason_counts[truncated] += 1
    if reason_counts:
        print("\n  Retry Reasons:")
        for reason, count in reason_counts.most_common():
            print(f"    {reason:<63} {count:>3}")

    # Latency
    elapsed = [c.elapsed for c in result.cases if c.elapsed > 0]
    if elapsed:
        elapsed_sorted = sorted(elapsed)
        avg = sum(elapsed) / len(elapsed)
        p95_idx = int(len(elapsed_sorted) * 0.95)
        p95 = elapsed_sorted[min(p95_idx, len(elapsed_sorted) - 1)]
        print("\n  Latency:")
        print(
            f"    min {elapsed_sorted[0]:.1f}s, avg {avg:.1f}s, "
            f"p95 {p95:.1f}s, max {elapsed_sorted[-1]:.1f}s"
        )

    # Category score breakdown
    cat_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cat_counts: Counter[str] = Counter()
    for case in result.cases:
        cat = case.category
        cat_counts[cat] += 1
        for metric, val in case.scores.items():
            cat_scores[cat][metric].append(val)
    if cat_scores:
        metrics = sorted({m for scores in cat_scores.values() for m in scores})
        header = f"    {'Category':<16}"
        for m in metrics:
            header += f"{m:>11}"
        header += f"{'n':>5}"
        print("\n  Scores by Category:")
        print(header)
        print("    " + "-" * (16 + 11 * len(metrics) + 5))
        for cat in sorted(cat_scores):
            row = f"    {cat:<16}"
            for m in metrics:
                vals = cat_scores[cat].get(m, [])
                avg = sum(vals) / len(vals) if vals else 0.0
                row += f"{avg:>11.2f}"
            row += f"{cat_counts[cat]:>5}"
            print(row)

    print()
