#!/usr/bin/env python3
"""A/B test prompt variants for constrained decoding questions.

Tests durability, affordance, and movement prompts against a small set
of objects to find which prompt style works best before running full evals.

Usage:
    uv run python backend/scripts/bench_prompt_variants.py [--repeat N]
"""

from __future__ import annotations

import asyncio
import io
import sys
from dataclasses import dataclass

# Force UTF-8 stdout for Rich output on Windows (cp1252 can't render box chars)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.creator.llm import ask_choice, ask_int, reset_agents


# ── Test objects: chosen to span each scale, NOT matching eval fixture examples ──

DURABILITY_TESTS: list[tuple[str, str]] = [
    # (object_name, expected_bucket) — "bucket" is approximate, not exact eval values
    ("tissue paper", "soft"),
    ("eggshell", "soft"),
    ("clay pot", "weak"),
    ("wine glass", "weak"),
    ("oak plank", "normal"),
    ("leather armor", "normal"),
    ("marble statue", "solid"),
    ("granite block", "solid"),
    ("titanium rod", "strong"),
    ("tungsten cube", "strong"),
    ("fortress gate", "iron"),
    ("bunker wall", "iron"),
    ("planet core", "permanent"),
    ("neutron star", "permanent"),
]

AFFORDANCE_TESTS: list[tuple[str, str]] = [
    ("coin", "carry"),
    ("dagger", "carry"),
    ("book", "carry"),
    ("camel", "ride"),
    ("motorcycle", "ride"),
    ("raft", "ride"),
    ("rope", "scale"),
    ("vine wall", "scale"),
    ("lighthouse", "scale"),
    ("volcano", "none"),
    ("campfire", "none"),
    ("cloud", "none"),
]

MOVEMENT_TESTS: list[tuple[str, str, str]] = [
    # (creature, target, expected_movement)
    ("lion", "gazelle", "seek"),
    ("hawk", "mouse", "seek"),
    ("cow", "hay bale", "seek"),
    ("ant", "sugar cube", "seek"),
    ("deer", "wolf", "run"),
    ("mouse", "cat", "run"),
    ("rabbit", "hawk", "run"),
    ("rock golem", "pebble", "ignore"),
    ("bear", "lamp post", "ignore"),
    ("eagle", "chair", "ignore"),
]


# ── Prompt variants ──

DURABILITY_VARIANTS: dict[str, tuple[tuple[str, ...], str]] = {
    "A_minimal": (
        ("soft", "weak", "normal", "solid", "strong", "iron", "permanent"),
        "Rate this object's durability.",
    ),
    "B_old_style": (
        ("soft", "weak", "normal", "solid", "strong", "iron", "permanent"),
        (
            "Rate the durability of the given object. "
            "soft=fragile (tissue, egg) weak=breaks easily (ceramic, leaf) "
            "normal=moderate (wood, cloth) solid=tough (brick, shell) "
            "strong=very hard (iron, gem) iron=fortified (concrete, armor) "
            "permanent=indestructible (planet)."
        ),
    ),
    "C_scale_desc": (
        ("soft", "weak", "normal", "solid", "strong", "iron", "permanent"),
        (
            "How easily does this object break? "
            "soft=crumbles on touch, weak=breaks from a drop, "
            "normal=survives casual handling, solid=resists strong force, "
            "strong=requires extreme force to damage, "
            "iron=nearly indestructible, permanent=cannot be destroyed."
        ),
    ),
    "D_comparison": (
        ("soft", "weak", "normal", "solid", "strong", "iron", "permanent"),
        (
            "Rate this object's durability from soft to permanent. "
            "Most everyday objects are normal. Lighter/weaker materials are soft or weak. "
            "Metals and minerals are strong or iron. "
            "Only geological features are permanent."
        ),
    ),
}

AFFORDANCE_VARIANTS: dict[str, tuple[tuple[str, ...], str]] = {
    "A_minimal": (
        ("carry", "ride", "scale", "none"),
        "How can a player interact with this object in a 2D game?",
    ),
    "B_old_style": (
        ("carry", "ride", "scale", "none"),
        (
            "In a 2D game, how can a player interact with this object? "
            "carry=pick up and hold, ride=sit on top and move, "
            "scale=climb up it, none=cannot interact physically."
        ),
    ),
    "C_size_framing": (
        ("carry", "ride", "scale", "none"),
        (
            "In a 2D game: carry=objects small enough to pick up, "
            "ride=vehicles or mounts the player sits on, "
            "scale=tall structures the player climbs, "
            "none=too dangerous or large to physically interact with."
        ),
    ),
}

# Movement: also test different word choices for "flee"
MOVEMENT_VARIANTS: dict[str, tuple[tuple[str, ...], dict[str, int], str]] = {
    "A_seek_run_ignore": (
        ("seek", "run", "ignore"),
        {"seek": 0, "run": 1, "ignore": 2},
        (
            "A creature sees a target in a 2D game. "
            "seek=move toward, run=run away, ignore=no interest. Return one word."
        ),
    ),
    "B_seek_avoid_ignore": (
        ("seek", "avoid", "ignore"),
        {"seek": 0, "avoid": 1, "ignore": 2},
        (
            "A creature sees a target in a 2D game. "
            "seek=move toward, avoid=move away, ignore=no interest. Return one word."
        ),
    ),
    "C_seek_escape_ignore": (
        ("seek", "escape", "ignore"),
        {"seek": 0, "escape": 1, "ignore": 2},
        (
            "A creature sees a target in a 2D game. "
            "seek=approach to interact, escape=flee from danger, "
            "ignore=no interest. Return one word."
        ),
    ),
    "D_hunt_avoid_ignore": (
        ("hunt", "avoid", "ignore"),
        {"hunt": 0, "avoid": 1, "ignore": 2},
        (
            "A creature sees a target in a 2D game. "
            "hunt=approach the target, avoid=stay away from the target, "
            "ignore=no interest. Return one word."
        ),
    ),
}


@dataclass
class Result:
    variant: str
    field: str
    obj_name: str
    expected: str
    got: str
    correct: bool


async def bench_durability(repeat: int) -> list[Result]:
    results = []
    for variant_name, (choices, instructions) in DURABILITY_VARIANTS.items():
        for obj_name, expected in DURABILITY_TESTS:
            for _ in range(repeat):
                got = await ask_choice(obj_name, choices, default="normal", instructions=instructions)
                # Allow ±1 bucket tolerance for "close enough"
                choice_list = list(choices)
                got_idx = choice_list.index(got) if got in choice_list else -1
                exp_idx = choice_list.index(expected)
                correct = abs(got_idx - exp_idx) <= 1
                results.append(Result(variant_name, "durability", obj_name, expected, got, correct))
    return results


async def bench_affordance(repeat: int) -> list[Result]:
    results = []
    for variant_name, (choices, instructions) in AFFORDANCE_VARIANTS.items():
        for obj_name, expected in AFFORDANCE_TESTS:
            for _ in range(repeat):
                got = await ask_choice(
                    obj_name, choices, default="none", instructions=instructions
                )
                correct = got == expected
                results.append(
                    Result(variant_name, "affordance", obj_name, expected, got, correct)
                )
    return results


async def bench_movement(repeat: int) -> list[Result]:
    results = []
    for variant_name, (choices, label_map, instructions) in MOVEMENT_VARIANTS.items():
        # Reverse map: int → word for this variant
        int_to_word = {v: k for k, v in label_map.items()}
        seek_word = int_to_word[0]
        flee_word = int_to_word[1]
        ignore_word = int_to_word[2]
        # Map canonical expected ("seek"/"run"/"ignore") to this variant's words
        canonical_to_variant = {"seek": seek_word, "run": flee_word, "ignore": ignore_word}

        for creature, target, expected_canonical in MOVEMENT_TESTS:
            expected_word = canonical_to_variant[expected_canonical]
            for _ in range(repeat):
                prompt = f"{creature} sees {target}."
                got = await ask_choice(
                    prompt, choices, default=ignore_word, instructions=instructions
                )
                correct = got == expected_word
                results.append(
                    Result(variant_name, "movement", f"{creature}→{target}", expected_word, got, correct)
                )
    return results


def print_summary(results: list[Result], field: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {field.upper()} VARIANTS")
    print(f"{'='*60}")

    variants = sorted(set(r.variant for r in results))
    for v in variants:
        v_results = [r for r in results if r.variant == v]
        n_correct = sum(1 for r in v_results if r.correct)
        n_total = len(v_results)
        pct = 100 * n_correct / n_total if n_total else 0
        print(f"\n  {v}: {pct:.0f}% ({n_correct}/{n_total})")
        # Show failures
        failures = [r for r in v_results if not r.correct]
        for r in failures:
            print(f"    ✗ {r.obj_name}: expected={r.expected}, got={r.got}")


async def main() -> None:
    repeat = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "--repeat" else 2
    if "--repeat" in sys.argv:
        idx = sys.argv.index("--repeat")
        repeat = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 2

    # Health check
    reset_agents()
    result = await ask_int("Reply with 1.", 0, 1, -1)
    if result == -1:
        print("LLM unreachable. Start with `make gpu` or configure cloud.")
        sys.exit(1)
    reset_agents()

    print(f"Running prompt variant bench (repeat={repeat})...")

    dur_results = await bench_durability(repeat)
    print_summary(dur_results, "durability")

    aff_results = await bench_affordance(repeat)
    print_summary(aff_results, "affordance")

    mov_results = await bench_movement(repeat)
    print_summary(mov_results, "movement")


if __name__ == "__main__":
    asyncio.run(main())
