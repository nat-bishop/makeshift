"""Distribution analysis for creator agent eval outputs.

Aggregates tag, behavior, and size frequencies across all cases
in an evaluation report to show variety and output patterns.
"""

from __future__ import annotations

import json
from collections import Counter

from app.models.behaviors import BehaviorParseError, compute_spec_cost, parse_behavior_string
from app.models.tags import TAG_POWER_COSTS, Tag
from pydantic_evals.reporting import EvaluationReport


def print_distribution_report(report: EvaluationReport) -> None:
    """Parse all outputs in a report and print aggregate distribution stats."""
    tag_counts: Counter[str] = Counter()
    trigger_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    behavior_count_dist: Counter[int] = Counter()
    tag_budgets: list[float] = []
    behavior_budgets: list[float] = []
    total = 0
    parse_errors = 0

    for case in report.cases:
        try:
            data = json.loads(case.output)
        except (json.JSONDecodeError, TypeError):
            parse_errors += 1
            continue

        total += 1

        # Tags
        tags = data.get("tags", [])
        for tag in tags:
            tag_counts[str(tag)] += 1

        # Tag budget
        try:
            cost = sum(TAG_POWER_COSTS.get(Tag(t), 0) for t in tags)
            tag_budgets.append(cost)
        except (ValueError, KeyError):
            pass

        # Size
        vd = data.get("visual_descriptor", {})
        size = vd.get("size_category", "unknown") if isinstance(vd, dict) else "unknown"
        size_counts[size] += 1

        # Behaviors
        raw_behaviors = data.get("behaviors", [])
        behavior_count_dist[len(raw_behaviors)] += 1
        bcost = 0
        for b in raw_behaviors:
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

    # Tag frequency
    print("\n  Tag Frequency:")
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

    if parse_errors:
        print(f"\n  ({parse_errors} outputs failed JSON parsing)")

    print()
