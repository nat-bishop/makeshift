"""Generate human-readable markdown reports from eval results.

V2: reports substance, element, tags, behavior verbs.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.models.tags import LLM_VISIBLE_TAGS_V2

from evals.models import EvalRunResult

ALL_V2_TAGS = sorted(t.value for t in LLM_VISIBLE_TAGS_V2)

_SCORE_METRICS = {
    "Validity", "Substance Accuracy", "Element Accuracy", "Tag Recall",
    "Faithfulness", "Gameplay Quality", "Sprite Prompt",
}
_COUNT_METRICS = {"Interaction Surface"}


def _fmt_score(metric: str, value: float) -> str:
    if metric in _COUNT_METRICS:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _section_overview(result: EvalRunResult) -> str:
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    score_order = [
        "Validity", "Substance Accuracy", "Element Accuracy", "Tag Recall",
        "Faithfulness", "Gameplay Quality", "Sprite Prompt",
    ]
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


def _section_distribution(result: EvalRunResult) -> str:
    tag_counts: Counter[str] = Counter()
    substance_counts: Counter[str] = Counter()
    element_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    verb_counts: Counter[str] = Counter()
    total = 0

    for case in result.cases:
        if case.output is None:
            continue
        total += 1
        out = case.output
        for tag in out.tags:
            tag_counts[tag] += 1
        size_counts[out.size_category] += 1
        if out.substance:
            substance_counts[out.substance] += 1
        if out.element:
            element_counts[out.element] += 1
        for b in out.resolved_behaviors:
            verb = b.split(" ")[0] if b else ""
            if verb:
                verb_counts[verb] += 1

    if total == 0:
        return "## Distribution\n\nNo parseable outputs.\n"

    lines = ["## Distribution", ""]

    # Substance frequency
    lines.extend([
        "### Substances", "", "| Substance | Count | Pct |", "|-----------|-------|-----|",
    ])
    for sub, count in substance_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {sub} | {count}/{total} | {pct:.0f}% |")

    # Element frequency
    lines.extend(["", "### Elements", "", "| Element | Count | Pct |", "|---------|-------|-----|"])
    no_elem = total - sum(element_counts.values())
    lines.append(f"| (none) | {no_elem}/{total} | {no_elem / total * 100:.0f}% |")
    for elem, count in element_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {elem} | {count}/{total} | {pct:.0f}% |")

    # Tag frequency
    lines.extend(["", "### Tags", "", "| Tag | Count | Pct | |", "|-----|-------|-----|---|"])
    for tag in ALL_V2_TAGS:
        tag_counts.setdefault(tag, 0)
    for tag, count in tag_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {tag} | {count}/{total} | {pct:.0f}% | `{_bar(pct)}` |")

    # Size distribution
    lines.extend(["", "### Sizes", "", "| Size | Count | Pct |", "|------|-------|-----|"])
    for size, count in size_counts.most_common():
        pct = count / total * 100
        lines.append(f"| {size} | {count}/{total} | {pct:.0f}% |")

    # Verb distribution
    if verb_counts:
        lines.extend(["", "### Behavior Verbs", "", "| Verb | Count |", "|------|-------|"])
        for verb, count in verb_counts.most_common():
            lines.append(f"| {verb} | {count} |")

    lines.append("")
    return "\n".join(lines)


def _section_category_scores(result: EvalRunResult) -> str:
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

    metrics = [
        "Validity", "Substance Accuracy", "Element Accuracy", "Tag Recall",
        "Faithfulness", "Gameplay Quality", "Sprite Prompt",
    ]
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

        # Substance + element + tags
        sub_str = out.substance or "(unknown)"
        elem_str = out.element or "(none)"
        tags_str = ", ".join(out.tags) if out.tags else "(none)"
        lines.append(
            f"**Substance:** {sub_str} | **Element:** {elem_str} | "
            f"**Tags:** {tags_str} | **Size:** {out.size_category}"
        )

        # Behaviors
        if out.resolved_behaviors:
            lines.append(
                f"**Behaviors ({len(out.resolved_behaviors)}):** "
                + ", ".join(f"`{b}`" for b in out.resolved_behaviors)
            )
        else:
            lines.append("*(no behaviors)*")

        # Scores
        score_parts = []
        for m in (
            "Validity", "Substance Accuracy", "Element Accuracy", "Tag Recall",
            "Faithfulness", "Gameplay Quality", "Sprite Prompt",
        ):
            if m in case.scores:
                score_parts.append(f"{m} {_fmt_score(m, case.scores[m])}")
        surface = case.scores.get("Interaction Surface")
        if surface is not None:
            score_parts.append(f"Surface {surface:.0f}")
        lines.append(f"**Scores:** {' | '.join(score_parts)}")

        # Reasons for imperfect scores
        for m in (
            "Substance Accuracy", "Element Accuracy", "Tag Recall",
            "Faithfulness", "Gameplay Quality", "Sprite Prompt",
        ):
            score = case.scores.get(m, 1.0)
            reason = case.reasons.get(m, "")
            if score < 1.0 and reason:
                lines.append(f"> **{m} ({_fmt_score(m, score)}):** {reason}")

        # Retry info
        if case.retries > 0:
            errors = "; ".join(case.retry_errors) if case.retry_errors else ""
            lines.append(f"> **Retries:** {case.retries}" + (f" — `{errors}`" if errors else ""))

        lines.append("")

    return "\n".join(lines)


def generate_markdown_report(result: EvalRunResult) -> str:
    sections = [
        _section_overview(result),
        _section_reliability(result),
        _section_category_scores(result),
        _section_distribution(result),
        _section_cases(result),
    ]
    return "\n".join(sections)
