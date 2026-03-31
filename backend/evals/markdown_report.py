"""Generate human-readable markdown reports from eval results.

Produces a scannable .md file alongside the JSON result:
overview at top, distributions in the middle, per-case details at bottom.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from app.models.behaviors import BehaviorParseError, parse_behavior_string
from app.models.tags import LLM_VISIBLE_TAGS

from evals.models import EvalRunResult

ALL_TAGS = sorted(t.value for t in LLM_VISIBLE_TAGS)

# Metrics that use 0-1 scale (formatted as .2f)
_SCORE_METRICS = {"Validity", "Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"}
# Metrics with special formatting
_COUNT_METRICS = {"Interaction Surface", "Has Signature"}


def _fmt_score(metric: str, value: float) -> str:
    """Format a score value based on metric type."""
    if metric in _COUNT_METRICS:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _bar(pct: float, width: int = 20) -> str:
    """Render a text bar chart segment."""
    filled = int(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _section_overview(result: EvalRunResult) -> str:
    """Run metadata and average scores."""
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    # Stable ordering for score metrics
    score_order = ["Validity", "Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"]
    lines = [
        f"# Eval: {result.name}",
        "",
        f"**{ts}** | Model: `{result.model}` | Judge: `{result.judge_model}` "
        f"| {result.dataset.total_cases} cases | Variant: `{result.variant}`",
        "",
        "## Scores",
        "",
        "| Metric | Mean |",
        "|--------|------|",
    ]
    for m in score_order:
        val = result.mean_scores.get(m, 0.0)
        lines.append(f"| {m} | {_fmt_score(m, val)} |")
    lines.append("")
    return "\n".join(lines)


def _section_reliability(result: EvalRunResult) -> str:
    """Retry and reliability stats."""
    rs = result.retry_stats
    lines = [
        "## Reliability",
        "",
        "| Stat | Value |",
        "|------|-------|",
        f"| First-try success | {rs.get('first_try_pct', 0):.0f}% "
        f"({int(rs.get('first_try_pct', 0) / 100 * result.dataset.total_cases)}"
        f"/{result.dataset.total_cases}) |",
        f"| Avg retries | {rs.get('mean', 0):.2f} |",
        f"| Max retries | {rs.get('max', 0)} |",
        f"| Total retries | {rs.get('total', 0)} |",
    ]

    # Retry reasons
    reason_counts: Counter[str] = Counter()
    for case in result.cases:
        for err in case.retry_errors:
            reason_counts[err] += 1
    if reason_counts:
        lines.extend(["", "**Retry reasons:**", ""])
        for reason, count in reason_counts.most_common():
            lines.append(f"- ({count}x) `{reason}`")

    lines.append("")
    return "\n".join(lines)


def _section_programmatic(result: EvalRunResult) -> str:
    """Programmatic metric summaries."""
    # Interaction surface
    surfaces = [c.scores.get("Interaction Surface", 0) for c in result.cases if c.output]
    avg_surface = sum(surfaces) / len(surfaces) if surfaces else 0
    min_surface = min(surfaces) if surfaces else 0
    max_surface = max(surfaces) if surfaces else 0

    # Has Signature (LIVING objects)
    living_cases = [c for c in result.cases if c.output and "LIVING" in c.output.tags]
    living_no_sig = [c for c in result.cases if c.scores.get("Has Signature") == 0.0]

    # Signature rate overall
    sig_cases = [c for c in result.cases if c.output and c.output.signature]

    # Visual description lengths
    vd_lengths = [
        len(c.output.visual_description) for c in result.cases
        if c.output and c.output.visual_description
    ]
    vd_min = min(vd_lengths) if vd_lengths else 0
    vd_max = max(vd_lengths) if vd_lengths else 0
    vd_median = int(median(vd_lengths)) if vd_lengths else 0
    vd_short = sum(1 for length in vd_lengths if length < 40)

    lines = [
        "## Programmatic Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Interaction Surface (avg) | {avg_surface:.1f} / 53 rules "
        f"(min {min_surface:.0f}, max {max_surface:.0f}) |",
        f"| Signature rate | {len(sig_cases)} / {result.dataset.total_cases} objects |",
        f"| LIVING w/o signature | {len(living_no_sig)} / {len(living_cases)} LIVING objects |",
        f"| Visual desc length | {vd_min} / {vd_median} / {vd_max} chars "
        f"(min / median / max) |",
    ]
    if vd_short:
        lines.append(f"| Visual desc < 40 chars | {vd_short} |")

    # List the LIVING objects without signature
    if living_no_sig:
        names = ", ".join(c.case for c in living_no_sig)
        lines.extend(["", f"**LIVING without signature:** {names}"])

    lines.append("")
    return "\n".join(lines)


def _section_distribution(result: EvalRunResult) -> str:
    """Tag, size, behavior distributions."""
    tag_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    sig_trigger_counts: Counter[str] = Counter()
    sig_action_counts: Counter[str] = Counter()
    resolved_behavior_dist: Counter[int] = Counter()
    total = 0
    with_sig = 0

    for case in result.cases:
        if case.output is None:
            continue
        total += 1
        out = case.output
        for tag in out.tags:
            tag_counts[tag] += 1
        size_counts[out.size_category] += 1
        resolved_behavior_dist[len(out.resolved_behaviors)] += 1
        if out.signature:
            with_sig += 1
            try:
                spec = parse_behavior_string(str(out.signature))
                sig_trigger_counts[spec.trigger.value] += 1
                sig_action_counts[spec.action.value] += 1
            except (BehaviorParseError, ValueError):
                pass

    if total == 0:
        return "## Distribution\n\nNo parseable outputs.\n"

    lines = ["## Distribution", ""]

    # Tag frequency
    lines.extend(["### Tags", "", "| Tag | Count | Pct | |", "|-----|-------|-----|---|"])
    for tag in ALL_TAGS:
        tag_counts.setdefault(tag, 0)
    for tag, count in tag_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {tag} | {count}/{total} | {pct:.0f}% | `{_bar(pct)}` |")

    # Size distribution
    lines.extend([
        "", "### Sizes", "", "| Size | Count | Pct |", "|------|-------|-----|",
    ])
    for size, count in size_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {size} | {count}/{total} | {pct:.0f}% |")

    # Resolved behaviors per object (implied + signature)
    lines.extend([
        "", "### Resolved Behaviors Per Object (implied + signature)", "",
        "| Count | Objects | Pct |", "|-------|---------|-----|",
    ])
    for n in sorted(resolved_behavior_dist):
        count = resolved_behavior_dist[n]
        pct = count / total * 100
        lines.append(f"| {n} | {count}/{total} | {pct:.0f}% |")

    # Signature trigger/action distribution
    if sig_trigger_counts:
        lines.extend([
            "", "### Signature Triggers", "", "| Type | Count |", "|------|-------|",
        ])
        for item, count in sig_trigger_counts.most_common():
            lines.append(f"| {item} | {count} |")

    if sig_action_counts:
        lines.extend([
            "", "### Signature Actions", "", "| Type | Count |", "|------|-------|",
        ])
        for item, count in sig_action_counts.most_common():
            lines.append(f"| {item} | {count} |")

    lines.append("")
    return "\n".join(lines)


def _section_category_scores(result: EvalRunResult) -> str:
    """Score breakdown by category."""
    cat_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cat_counts: Counter[str] = Counter()
    for case in result.cases:
        cat = case.category
        cat_counts[cat] += 1
        for metric, val in case.scores.items():
            if metric in _SCORE_METRICS:
                cat_scores[cat][metric].append(val)

    if not cat_scores:
        return ""

    metrics = ["Validity", "Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"]
    header = "| Category | " + " | ".join(metrics) + " | n |"
    sep = "|----------|" + "|".join("-" * (len(m) + 2) for m in metrics) + "|---|"

    lines = ["## Scores by Category", "", header, sep]
    for cat in sorted(cat_scores):
        row = f"| {cat} |"
        for m in metrics:
            vals = cat_scores[cat].get(m, [])
            avg = sum(vals) / len(vals) if vals else 0.0
            row += f" {avg:.2f} |"
        row += f" {cat_counts[cat]} |"
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def _section_cases(result: EvalRunResult) -> str:
    """Per-case details with scores and reasons for imperfect results."""
    lines = ["## Cases", ""]

    for case in result.cases:
        lines.append(f"### {case.case}")

        if case.error:
            lines.append(f"**ERROR:** `{case.error}`")
            if case.retries:
                lines.append(f"**Retries:** {case.retries}")
            lines.append("")
            continue

        if case.output is None:
            lines.append("*No output*\n")
            continue

        out = case.output

        # Tags and size
        tags_str = ", ".join(out.tags) if out.tags else "(none)"
        lines.append(f"**Tags:** {tags_str} | **Size:** {out.size_category}")

        # Signature + resolved behaviors
        if out.signature:
            lines.append(f"**Signature:** `{out.signature}`")
        if out.resolved_behaviors:
            lines.append(f"**Behaviors ({len(out.resolved_behaviors)}):** "
                         + ", ".join(f"`{b}`" for b in out.resolved_behaviors))
        else:
            lines.append("*(no behaviors)*")

        # Scores line
        score_parts = []
        for m in ("Validity", "Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"):
            if m in case.scores:
                score_parts.append(f"{m} {_fmt_score(m, case.scores[m])}")
        surface = case.scores.get("Interaction Surface")
        if surface is not None:
            score_parts.append(f"Surface {surface:.0f}")
        lines.append(f"**Scores:** {' | '.join(score_parts)}")

        # Reasons for imperfect scores only
        for m in ("Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"):
            score = case.scores.get(m, 1.0)
            reason = case.reasons.get(m, "")
            if score < 1.0 and reason:
                lines.append(f"> **{m} ({_fmt_score(m, score)}):** {reason}")

        # Has Signature warning
        if case.scores.get("Has Signature") == 0.0:
            lines.append("> **Note:** LIVING object with no signature behavior")

        # Retry info
        if case.retries > 0:
            errors = "; ".join(case.retry_errors) if case.retry_errors else ""
            lines.append(f"> **Retries:** {case.retries}" + (f" — `{errors}`" if errors else ""))

        lines.append("")

    return "\n".join(lines)


def generate_markdown_report(result: EvalRunResult) -> str:
    """Generate a complete human-readable markdown report."""
    sections = [
        _section_overview(result),
        _section_reliability(result),
        _section_programmatic(result),
        _section_category_scores(result),
        _section_distribution(result),
        _section_cases(result),
    ]
    return "\n".join(sections)
