"""Distribution analysis for creator agent eval outputs.

Aggregates tag, behavior, and size frequencies across all cases
in a saved EvalRunResult to show variety and output patterns.
"""

from __future__ import annotations

from collections import Counter

from app.models.behaviors import BehaviorParseError, compute_spec_cost, parse_behavior_string
from app.models.tags import TAG_POWER_COSTS, Tag

from evals.models import EvalRunResult

ALL_TAGS = [t.value for t in Tag]


def print_distribution_report(result: EvalRunResult) -> None:
    """Print aggregate distribution stats from a saved eval result."""
    tag_counts: Counter[str] = Counter()
    trigger_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    behavior_count_dist: Counter[int] = Counter()
    tag_budgets: list[float] = []
    behavior_budgets: list[float] = []
    total = 0

    for case in result.cases:
        if case.output is None:
            continue
        total += 1
        out = case.output

        # Tags
        for tag in out.tags:
            tag_counts[tag] += 1

        # Tag budget
        try:
            cost = sum(TAG_POWER_COSTS.get(Tag(t), 0) for t in out.tags)
            tag_budgets.append(cost)
        except (ValueError, KeyError):
            pass

        # Size
        size_counts[out.size_category] += 1

        # Behaviors
        behavior_count_dist[len(out.behaviors)] += 1
        bcost = 0
        for b in out.behaviors:
            try:
                spec = parse_behavior_string(str(b))
                trigger_counts[spec.trigger.value] += 1
                action_counts[spec.action.value] += 1
                target_counts[spec.target.value] += 1
                bcost += compute_spec_cost(spec)
            except (BehaviorParseError, ValueError):
                pass
        behavior_budgets.append(bcost)

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

    # Behavior count
    print("\n  Behaviors Per Object:")
    for n in sorted(behavior_count_dist):
        count = behavior_count_dist[n]
        pct = count / total * 100
        print(f"    {n} behaviors: {count:>3}/{total}  ({pct:4.0f}%)")

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

    # Budget utilization
    if tag_budgets:
        avg_tag = sum(tag_budgets) / len(tag_budgets)
        max_tag = max(tag_budgets)
        print("\n  Budget Utilization:")
        print(f"    Tag budget:      avg {avg_tag:.1f}/10, max {max_tag:.0f}/10")
    if behavior_budgets:
        avg_beh = sum(behavior_budgets) / len(behavior_budgets)
        max_beh = max(behavior_budgets)
        print(f"    Behavior budget: avg {avg_beh:.1f}/8,  max {max_beh:.0f}/8")

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

    print()
