"""Test different creator agent temperatures on the same cases.

Generates outputs at each temperature, scores them all with the same judge,
then compares quality metrics.

Usage:
    cd backend && uv run python -m evals.run_temp_experiment
    cd backend && uv run python -m evals.run_temp_experiment --temps 0.5,0.8,1.0,1.2
    cd backend && uv run python -m evals.run_temp_experiment --cases "fire sword,rock,rubber armor"
"""

from __future__ import annotations

import argparse
import asyncio
from statistics import mean

import logfire
from app.config import settings
from app.creator.agent import _build_model
from app.models.blueprint import CreatorOutput
from pydantic_ai import Agent
from pydantic_evals import Dataset

from evals.conftest import make_task
from evals.dataset import EVAL_CASES
from evals.io import report_to_result, save_result
from evals.metrics import default_evaluators
from evals.prompts import PROMPT_VARIANTS


def _make_agent_with_overrides(
    system_prompt: str,
    temperature: float,
    top_p: float | None = None,
) -> Agent[None, CreatorOutput]:
    """Build a PydanticAI agent with specific sampling overrides."""
    model_settings: dict = {
        "timeout": settings.llm_timeout_seconds,
        "temperature": temperature,
        "top_p": top_p if top_p is not None else settings.llm_top_p,
        "presence_penalty": settings.llm_presence_penalty,
    }
    if settings.local_llm_url:
        model_settings["extra_body"] = {
            "top_k": settings.llm_top_k,
            "min_p": settings.llm_min_p,
            "repetition_penalty": settings.llm_repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": not settings.local_llm_thinking_disabled},
        }

    return Agent(
        _build_model(),
        output_type=CreatorOutput,
        retries=3,
        system_prompt=system_prompt,
        model_settings=model_settings,
    )




def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test creator agent at different temperatures")
    parser.add_argument(
        "--temps",
        default="0.4,0.6,0.8,1.0,1.2",
        help="Comma-separated temperature values to test (default: 0.4,0.6,0.8,1.0,1.2)",
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Comma-separated case names (default: 20 representative cases)",
    )
    parser.add_argument(
        "--variant",
        default="baseline",
        help="Prompt variant (default: baseline)",
    )
    parser.add_argument(
        "--top-p",
        default=None,
        help="Comma-separated top_p values to test (default: use .env value for all temps)",
    )
    return parser.parse_args()


# Default 20 representative cases spanning all categories
DEFAULT_CASES = [
    "rock", "fire sword", "explosive barrel", "glass cannon", "sticky honey trap",
    "acid spider", "friendly dog", "lava monster", "wind spirit", "cowardly slime",
    "the sun", "sadness", "indestructible wall", "fiar swrod", "rubber armor",
    "helicopter", "campfire", "magnet", "health potion", "tornado",
]


async def main():
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")
    logfire.instrument_pydantic_ai()

    args = parse_args()
    temps = [float(t.strip()) for t in args.temps.split(",")]
    top_ps = [float(p.strip()) for p in args.top_p.split(",")] if args.top_p else [None] * len(temps)
    if len(top_ps) == 1 and len(temps) > 1:
        top_ps = top_ps * len(temps)
    variant = args.variant
    system_prompt = PROMPT_VARIANTS[variant]

    if args.cases:
        requested = {c.strip().lower() for c in args.cases.split(",")}
        cases = [c for c in EVAL_CASES if c.name.lower() in requested]
    else:
        requested = {c.lower() for c in DEFAULT_CASES}
        cases = [c for c in EVAL_CASES if c.name.lower() in requested]

    # Build experiment configs: list of (label, temp, top_p)
    experiments = []
    for i, temp in enumerate(temps):
        tp = top_ps[i] if i < len(top_ps) else None
        label = f"temp_{temp:.1f}".replace(".", "_")
        if tp is not None:
            label += f"_tp{tp:.1f}".replace(".", "_")
        experiments.append((label, temp, tp))

    print(f"Testing {len(experiments)} configs:")
    for label, temp, tp in experiments:
        tp_str = f", top_p={tp}" if tp is not None else ""
        print(f"  {label}: temp={temp}{tp_str}")
    print(f"Cases: {len(cases)}")
    print(f"Model: {settings.llm_model}\n")

    all_results = {}

    for name, temp, tp in experiments:
        tp_str = f", top_p={tp}" if tp is not None else ""
        print(f"\n{'=' * 60}")
        print(f"  {name}: temp={temp}{tp_str} — {len(cases)} cases")
        print(f"{'=' * 60}")

        agent = _make_agent_with_overrides(system_prompt, temp, tp)
        dataset = Dataset(cases=list(cases), evaluators=default_evaluators())
        report = await dataset.evaluate(make_task(agent), name=name, max_concurrency=8)

        result = report_to_result(report, variant, settings.llm_model, name=name)
        run_dir = save_result(result)
        all_results[name] = result
        print(f"Saved to {run_dir}")

    # Summary comparison
    metrics = ["Validity", "Tag Recall", "Faithfulness", "Gameplay Quality", "Sprite Prompt"]
    count_metrics = ["Interaction Surface", "Has Signature"]

    labels = [name for name, _, _ in experiments]

    print(f"\n{'=' * 90}")
    print("  COMPARISON SUMMARY")
    print(f"{'=' * 90}")

    # Header
    col_w = max(len(l) for l in labels) + 2
    print(f"\n{'Metric':<22}", end="")
    for label in labels:
        print(f"  {label:>{col_w}}", end="")
    print()
    print("-" * (22 + (col_w + 2) * len(labels)))

    for m in metrics:
        print(f"{m:<22}", end="")
        for label in labels:
            val = all_results[label].mean_scores.get(m, 0)
            print(f"  {val:>{col_w}.2f}", end="")
        print()

    for m in count_metrics:
        print(f"{m:<22}", end="")
        for label in labels:
            val = all_results[label].mean_scores.get(m, 0)
            print(f"  {val:>{col_w}.1f}", end="")
        print()

    # Retry stats
    print(f"\n{'Retries (total)':<22}", end="")
    for label in labels:
        val = all_results[label].retry_stats.get("total", 0)
        print(f"  {val:>{col_w}}", end="")
    print()

    print(f"{'First-try %':<22}", end="")
    for label in labels:
        val = all_results[label].retry_stats.get("first_try_pct", 0)
        print(f"  {val:>{col_w - 1}.0f}%", end="")
    print()

    # Per-category breakdown
    print("\n--- Gameplay Quality by Category ---\n")
    cats = sorted({c.category for c in all_results[labels[0]].cases})
    print(f"{'Category':<22}", end="")
    for label in labels:
        print(f"  {label:>{col_w}}", end="")
    print()
    print("-" * (22 + (col_w + 2) * len(labels)))

    for cat in cats:
        print(f"{cat:<22}", end="")
        for label in labels:
            vals = [
                c.scores.get("Gameplay Quality", 0)
                for c in all_results[label].cases
                if c.category == cat and c.scores
            ]
            avg = mean(vals) if vals else 0
            print(f"  {avg:>{col_w}.2f}", end="")
        print()


if __name__ == "__main__":
    asyncio.run(main())
