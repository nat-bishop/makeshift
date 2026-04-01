"""A/B test judge rubric variants on the same cached outputs.

Generates one set of outputs, then scores them with different judge configs
to isolate judge variance from agent variance.

Usage:
    cd backend && uv run python -m evals.run_judge_experiment
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import logfire
from pydantic_ai.settings import ModelSettings
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge

from evals.dataset import CaseMeta
from evals.io import load_result, report_to_result, save_result
from evals.metrics import JUDGE_SETTINGS, RUBRICS, default_evaluators
from evals.metrics.interaction_surface import InteractionSurfaceEvaluator
from evals.metrics.living_movement import HasSignatureEvaluator
from evals.metrics.rubric_context import get_rules_summary_string, get_tag_list_string
from evals.metrics.tag_recall import TagRecallEvaluator
from evals.metrics.validity import ValidityEvaluator

# The original rubrics before scored examples / tighter boundaries
_TAG_LIST = get_tag_list_string()
_RULES_SUMMARY = get_rules_summary_string()
from app.engine.rules_data import ALL_RULES

ORIGINAL_RUBRICS: dict[str, str] = {
    "Faithfulness": (
        "You are evaluating a game object design for a 2D physics sandbox game "
        "(like Scribblenauts). A player typed a description, and an AI designed a "
        "game object with a name, tags, behaviors, and visual description.\n\n"
        "Evaluate whether the design faithfully represents what the player asked for.\n\n"
        "Score on this scale:\n"
        "- 1.0: The design captures the core concept perfectly. Tags, behaviors, and "
        "visuals all reinforce the player's intent. No irrelevant or contradictory elements.\n"
        "- 0.75: The design captures the main idea with minor issues — one slightly off "
        "tag, a missing but non-critical behavior, or a small visual mismatch.\n"
        "- 0.5: The design partially captures the concept but has notable gaps — missing "
        "a key tag that defines the object, or includes behaviors/tags that don't fit "
        "the description.\n"
        "- 0.25: The design misses the core concept — wrong physical properties, "
        "contradictory theme, or behaviors that work against the player's intent.\n"
        "- 0.0: The design bears no meaningful relationship to the player's description.\n\n"
        "Focus on: Does the name match the concept? Do the tags reflect the object's "
        "core physical nature? Do the behaviors match what the player described or "
        "implied? Does the visual description match the tags and name?\n\n"
        f"VALID TAGS (only these exist — no others):\n{_TAG_LIST}\n\n"
        "Do NOT penalize the design for missing tags that don't exist in this list "
        "(e.g., there is no EDIBLE, FOOD, WOODEN, or METAL tag)."
    ),
    "Gameplay Quality": (
        "You are evaluating a game object design for a 2D physics sandbox where objects "
        "interact through a TAG SYSTEM. Tags create automatic interactions — this is "
        "the core of the game's emergent gameplay.\n\n"
        f"VALID TAGS (1-4 per object):\n{_TAG_LIST}\n\n"
        f"COMPLETE TAG INTERACTION RULES ({len(ALL_RULES)} rules — "
        "these fire automatically, no behaviors needed):\n"
        f"{_RULES_SUMMARY}\n\n"
        "TAG-IMPLIED BEHAVIORS (automatic from tags, not authored by the designer):\n"
        "- HOSTILE + LIVING -> chases nearest creature, flees when hurt\n"
        "- LIVING (alone) -> wanders passively\n"
        "- EXPLOSIVE -> detonates when damaged\n\n"
        "SIGNATURE BEHAVIOR (optional, at most 1 per object):\n"
        "A single unique behavior that makes this specific object unusual — "
        "ranged attacks, healing, tag mutation, or reactive transformations. "
        "Most objects don't need one. Tags + implied behaviors handle the rest.\n"
        "- ADD_TAGS is especially powerful — it can spread tags to other objects, "
        "creating chain reactions\n\n"
        "Evaluate the GAMEPLAY QUALITY of this design — does it create interesting "
        "interactions?\n\n"
        "Score on this scale:\n"
        "- 1.0: Excellent design that exploits the tag system for emergent gameplay. "
        "Tags chosen create interesting interaction surfaces with other objects. "
        "Signature behavior (if present) complements tags rather than duplicating "
        "what tags already do.\n"
        "- 0.75: Good design with minor missed opportunities. Core tags are right but "
        "one interaction opportunity missed (e.g., a wooden object without FLAMMABLE, "
        "or a creature with only HOSTILE instead of using richer tag interactions).\n"
        "- 0.5: Mediocre design. Falls into the 'generic damage' trap — uses only "
        "HOSTILE when tags like HEAT_SOURCE, SHARP, ACIDIC, or "
        "TOXIC would create richer interactions automatically. Or has tags that don't "
        "create any meaningful interaction surfaces.\n"
        "- 0.25: Poor design. Tags and signature work against each other, or the "
        "object is inert when it should be interactive.\n"
        "- 0.0: No useful gameplay properties. Wrong tags, no interaction surfaces, "
        "completely generic.\n\n"
        "KEY PRINCIPLE: Tags are the primary gameplay driver. Simple objects with "
        "well-chosen tags CAN score 1.0."
    ),
    "Sprite Prompt": RUBRICS["Sprite Prompt"],
}

REPEAT = 5
GENERATED_DIR = "evals/results/20260401_034005_baseline"

EXPERIMENTS = {
    "v2_temp0": {
        "desc": "New rubrics (scored examples + tight boundaries) + temp=0",
        "rubrics": RUBRICS,
        "settings": ModelSettings(temperature=0.0),
    },
    "v1_temp0": {
        "desc": "Original rubrics + temp=0",
        "rubrics": ORIGINAL_RUBRICS,
        "settings": ModelSettings(temperature=0.0),
    },
    "v1_default": {
        "desc": "Original rubrics + default temp",
        "rubrics": ORIGINAL_RUBRICS,
        "settings": None,
    },
}


def _make_evaluators(rubrics: dict[str, str], settings: ModelSettings | None) -> list:
    judges = [
        LLMJudge(
            rubric=rubrics[name],
            include_input=True,
            model_settings=settings,
            score={"evaluation_name": name, "include_reason": True},
            assertion=False,
        )
        for name in rubrics
    ]
    return [
        ValidityEvaluator(),
        TagRecallEvaluator(),
        InteractionSurfaceEvaluator(),
        HasSignatureEvaluator(),
        *judges,
    ]


async def run_experiment(
    name: str, rubrics: dict[str, str], settings: ModelSettings | None,
    cases: list[Case], outputs: dict[str, str],
) -> Path:
    async def cached_task(description: str) -> str:
        return outputs[description]

    evaluators = _make_evaluators(rubrics, settings)
    dataset = Dataset(cases=cases, evaluators=evaluators)
    report = await dataset.evaluate(
        cached_task, name=name, max_concurrency=8, repeat=REPEAT,
    )
    result = report_to_result(report, "baseline", "Qwen/Qwen3.5-35B-A3B-FP8", name=name)
    return save_result(result)


def analyze_variance(result_path: Path, label: str) -> dict[str, tuple[float, float]]:
    result = load_result(result_path)

    case_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for c in result.cases:
        base = c.case.rsplit(" [", 1)[0]
        for metric, score in c.scores.items():
            case_scores[base][metric].append(score)

    metrics = ["Faithfulness", "Gameplay Quality", "Sprite Prompt"]
    metric_stdevs: dict[str, list[float]] = defaultdict(list)

    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")
    print(f"{'Case':<25} {'Faithfulness':>14} {'Gameplay Q':>14} {'Sprite P':>14}")
    print("-" * 70)

    for case in sorted(case_scores):
        parts = []
        for m in metrics:
            vals = case_scores[case][m]
            if len(vals) >= 2:
                sd = stdev(vals)
                metric_stdevs[m].append(sd)
                avg = mean(vals)
                parts.append(f"{avg:.2f}+/-{sd:.2f}")
            else:
                parts.append("n/a")
        print(f"{case:<25} {parts[0]:>14} {parts[1]:>14} {parts[2]:>14}")

    print("-" * 70)
    result_dict = {}
    for m in metrics:
        avg_sd = mean(metric_stdevs[m]) if metric_stdevs[m] else 0
        max_sd = max(metric_stdevs[m]) if metric_stdevs[m] else 0
        result_dict[m] = (avg_sd, max_sd)
        print(f"  {m}: avg_stdev={avg_sd:.3f}, max_stdev={max_sd:.3f}")

    return result_dict


async def main():
    logfire.configure(send_to_logfire="if-token-present", service_name="makeshift-evals")

    existing = load_result(Path(GENERATED_DIR))
    outputs: dict[str, str] = {}
    cases: list[Case[str, str, CaseMeta]] = []
    for c in existing.cases:
        if not c.output_raw:
            continue
        outputs[c.inputs] = c.output_raw
        cases.append(Case(
            name=c.case,
            inputs=c.inputs,
            metadata=CaseMeta(category=c.category, expected_tags=c.expected_tags),
        ))

    print(f"Running {len(EXPERIMENTS)} experiments, {len(cases)} cases x {REPEAT} repeats each\n")

    all_results: dict[str, dict[str, tuple[float, float]]] = {}
    for exp_name, config in EXPERIMENTS.items():
        print(f"\n--- {exp_name}: {config['desc']} ---")
        run_dir = await run_experiment(
            exp_name, config["rubrics"], config["settings"], cases, outputs,
        )
        print(f"Saved to {run_dir}")
        all_results[exp_name] = analyze_variance(run_dir, f"{exp_name}: {config['desc']}")

    # Summary comparison
    metrics = ["Faithfulness", "Gameplay Quality", "Sprite Prompt"]
    print(f"\n{'=' * 80}")
    print("  COMPARISON SUMMARY (same 5 outputs scored 5x each)")
    print(f"{'=' * 80}")
    print(f"{'Experiment':<25}", end="")
    for m in metrics:
        print(f" {m:>18}", end="")
    print()
    print("-" * 80)
    for exp_name, stats in all_results.items():
        print(f"{exp_name:<25}", end="")
        for m in metrics:
            avg_sd, max_sd = stats.get(m, (0, 0))
            print(f" {avg_sd:.3f} (max {max_sd:.3f})", end="")
        print()


if __name__ == "__main__":
    asyncio.run(main())
