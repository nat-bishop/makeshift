"""Distribution analysis for V2 creator agent eval outputs.

Aggregates substance, element, tag, behavior verb, and size frequencies
across all cases in a saved EvalRunResult.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.models.tags import LLM_VISIBLE_TAGS_V2

from evals.models import EvalRunResult

ALL_V2_TAGS = sorted(t.value for t in LLM_VISIBLE_TAGS_V2)


def print_distribution_report(result: EvalRunResult) -> None:
    """Print aggregate distribution stats from a saved eval result."""
    tag_counts: Counter[str] = Counter()
    substance_counts: Counter[str] = Counter()
    element_counts: Counter[str] = Counter()
    verb_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    behavior_count_dist: Counter[int] = Counter()
    total = 0

    for case in result.cases:
        if case.output is None:
            continue
        total += 1
        out = case.output

        for tag in out.tags:
            tag_counts[tag] += 1

        size_counts[out.size_category] += 1

        # V2: substance and element
        if hasattr(out, "substance") and out.substance:
            substance_counts[out.substance] += 1
        if hasattr(out, "element") and out.element:
            element_counts[out.element] += 1

        # V2: behavior verbs
        behaviors = getattr(out, "behaviors", [])
        behavior_count_dist[len(behaviors)] += 1
        for b in behaviors:
            if isinstance(b, dict):
                verb_counts[b.get("verb", "unknown")] += 1
            elif hasattr(b, "verb"):
                verb_counts[b.verb] += 1

    if total == 0:
        print("\n  No parseable outputs for distribution analysis.\n")
        return

    print(f"\n{'=' * 60}")
    print(f"  Distribution Analysis ({total} objects)")
    print(f"{'=' * 60}")

    # Substance frequency
    if substance_counts:
        print("\n  Substance Frequency:")
        for sub, count in substance_counts.most_common():
            pct = count / total * 100
            bar = "#" * int(pct / 2)
            print(f"    {sub:<12} {count:>3}/{total}  ({pct:4.0f}%)  {bar}")

    # Element frequency
    print("\n  Element Frequency:")
    no_element = total - sum(element_counts.values())
    print(f"    {'(none)':<12} {no_element:>3}/{total}  ({no_element / total * 100:4.0f}%)")
    for elem, count in element_counts.most_common():
        pct = count / total * 100
        print(f"    {elem:<12} {count:>3}/{total}  ({pct:4.0f}%)")

    # Tag frequency
    print("\n  Tag Frequency:")
    for tag in ALL_V2_TAGS:
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

    # Behavior verb distribution
    if verb_counts:
        print("\n  Behavior Verbs:")
        for verb, count in verb_counts.most_common():
            print(f"    {verb:<20} {count:>3}")

    # Behavior count distribution
    print("\n  Behaviors per Object:")
    for n in sorted(behavior_count_dist):
        count = behavior_count_dist[n]
        print(f"    {n} behaviors: {count:>3}/{total}")

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
            reason_counts[err] += 1
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
