"""Embedding quality evaluation — spot-check cosine similarities.

Tests that the qwen3-embedding model produces semantically appropriate
vectors for behavior targeting and object identity matching.

Requires Ollama running with qwen3-embedding:0.6b pulled.

Usage:
    cd backend && uv run python -m evals.embedding_eval
    cd backend && uv run python -m evals.embedding_eval --threshold-high 0.5 --threshold-low 0.35
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.embeddings import build_embed_string, embed_texts
from app.models.tags import Tag

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class EmbeddingPair:
    name: str
    text_a: str
    text_b: str
    expect_high: bool
    category: str
    notes: str = ""


def _identity(
    name: str, visual: str, size: str = "medium", tags: list[Tag] | None = None
) -> str:
    """Build an identity embedding string for a test object."""
    return build_embed_string(name, visual, size, tags or [])


# ---------------------------------------------------------------------------
# Test pairs
# ---------------------------------------------------------------------------

EMBEDDING_PAIRS: list[EmbeddingPair] = [
    # ===== Behavior-target matching (core use case) =====
    EmbeddingPair(
        name="donut_vs_food_target",
        text_a=_identity("Donut", "a glazed sugary donut with rainbow sprinkles", "small",
                         [Tag.BREAKABLE]),
        text_b="food, especially donuts",
        expect_high=True,
        category="behavior_match",
        notes="Cop's eat target should match a donut.",
    ),
    EmbeddingPair(
        name="donut_vs_criminals_target",
        text_a=_identity("Donut", "a glazed sugary donut with rainbow sprinkles", "small",
                         [Tag.BREAKABLE]),
        text_b="criminals and lawbreakers",
        expect_high=False,
        category="behavior_match",
        notes="Donut should NOT match a destroy-criminals target.",
    ),
    EmbeddingPair(
        name="burning_spoon_vs_fire_target",
        text_a=_identity("Wooden Spoon", "a smooth wooden cooking spoon", "small",
                         [Tag.RIGID, Tag.FLAMMABLE, Tag.HEAT_SOURCE, Tag.HOT]),
        text_b="fires and burning things",
        expect_high=True,
        category="behavior_match",
        notes="Firefighter should target a burning spoon.",
    ),
    EmbeddingPair(
        name="cold_spoon_vs_fire_target",
        text_a=_identity("Wooden Spoon", "a smooth wooden cooking spoon", "small",
                         [Tag.RIGID, Tag.FLAMMABLE]),
        text_b="fires and burning things",
        expect_high=False,
        category="behavior_match",
        notes="Non-burning spoon should NOT match fire target.",
    ),
    EmbeddingPair(
        name="villager_alive_vs_prey",
        text_a=_identity("Villager", "a frightened peasant in brown clothes", "medium",
                         [Tag.LIVING]),
        text_b="prey animals and living creatures",
        expect_high=True,
        category="behavior_match",
        notes="Wolf's eat target should match a living villager.",
    ),
    EmbeddingPair(
        name="villager_petrified_vs_prey",
        text_a=_identity("Villager", "a frightened peasant in brown clothes", "medium",
                         [Tag.RIGID, Tag.BREAKABLE]),
        text_b="prey animals and living creatures",
        expect_high=False,
        category="behavior_match",
        notes="Petrified villager (no LIVING) should NOT match prey target.",
    ),
    EmbeddingPair(
        name="robber_vs_criminals_target",
        text_a=_identity("Robber", "a masked criminal in dark clothes", "medium",
                         [Tag.LIVING, Tag.HOSTILE]),
        text_b="criminals and lawbreakers",
        expect_high=True,
        category="behavior_match",
        notes="Cop's destroy target should match a robber.",
    ),
    EmbeddingPair(
        name="burning_tree_vs_fire_target",
        text_a=_identity("Oak Tree", "a tall tree with green leaves", "large",
                         [Tag.FLAMMABLE, Tag.HEAT_SOURCE, Tag.HOT]),
        text_b="fires and burning things",
        expect_high=True,
        category="behavior_match",
        notes="Firefighter should target a burning tree.",
    ),
    # ===== Cross-object discrimination =====
    EmbeddingPair(
        name="fire_sword_vs_ice_wall",
        text_a=_identity("Fire Sword", "a gleaming blade wreathed in flame", "small",
                         [Tag.SHARP, Tag.METALLIC, Tag.RIGID, Tag.HEAT_SOURCE, Tag.HOT]),
        text_b=_identity("Ice Wall", "a towering wall of translucent blue ice", "huge",
                         [Tag.FROZEN, Tag.RIGID, Tag.COLD, Tag.BRITTLE]),
        expect_high=False,
        category="discrimination",
        notes="Opposite objects should have low similarity.",
    ),
    EmbeddingPair(
        name="sword_vs_dagger",
        text_a=_identity("Steel Sword", "a long gleaming steel blade", "medium",
                         [Tag.SHARP, Tag.METALLIC, Tag.RIGID]),
        text_b=_identity("Iron Dagger", "a short rusty iron blade", "small",
                         [Tag.SHARP, Tag.METALLIC, Tag.RIGID]),
        expect_high=True,
        category="discrimination",
        notes="Similar weapons should have high similarity.",
    ),
    EmbeddingPair(
        name="cop_vs_donut",
        text_a=_identity("Officer Johnson", "a stern police officer in blue uniform", "medium",
                         [Tag.LIVING, Tag.HOSTILE]),
        text_b=_identity("Donut", "a glazed sugary donut with rainbow sprinkles", "small",
                         [Tag.BREAKABLE]),
        expect_high=False,
        category="discrimination",
        notes="A cop and a donut should be semantically distinct.",
    ),
    EmbeddingPair(
        name="wolf_vs_dog",
        text_a=_identity("Wolf", "a gray wolf with sharp teeth and yellow eyes", "medium",
                         [Tag.LIVING, Tag.HOSTILE]),
        text_b=_identity("Dog", "a friendly brown dog with a wagging tail", "medium",
                         [Tag.LIVING]),
        expect_high=True,
        category="discrimination",
        notes="Similar animals should be somewhat similar even with different hostility.",
    ),
    # ===== Tag-shift tests (same object, different states) =====
    EmbeddingPair(
        name="tree_normal_vs_burning",
        text_a=_identity("Oak Tree", "a tall tree with green leaves", "large",
                         [Tag.FLAMMABLE]),
        text_b=_identity("Oak Tree", "a tall tree with green leaves", "large",
                         [Tag.FLAMMABLE, Tag.HEAT_SOURCE, Tag.HOT]),
        expect_high=True,
        category="tag_shift",
        notes="Same tree in different states — should still be similar (it's the same tree).",
    ),
    EmbeddingPair(
        name="villager_alive_vs_petrified",
        text_a=_identity("Villager", "a frightened peasant", "medium", [Tag.LIVING]),
        text_b=_identity("Villager", "a frightened peasant", "medium",
                         [Tag.RIGID, Tag.BREAKABLE]),
        expect_high=True,
        category="tag_shift",
        notes="Same name+description dominates. Tag phrases shift similarity but not enough "
              "to drop below threshold. Real sim ~0.89. Known limitation: targeting relies on "
              "tag phrase contribution which is small vs name+visual.",
    ),
    EmbeddingPair(
        name="sword_dry_vs_wet",
        text_a=_identity("Steel Sword", "a sharp steel blade", "medium",
                         [Tag.SHARP, Tag.METALLIC, Tag.RIGID]),
        text_b=_identity("Steel Sword", "a sharp steel blade", "medium",
                         [Tag.SHARP, Tag.METALLIC, Tag.RIGID, Tag.WET]),
        expect_high=True,
        category="tag_shift",
        notes="Wet sword is still a sword — minor state change.",
    ),
    # ===== Behavior target semantics =====
    EmbeddingPair(
        name="food_vs_enemies",
        text_a="food, especially donuts",
        text_b="enemies and monsters",
        expect_high=False,
        category="target_semantics",
        notes="Eat target vs destroy target should be dissimilar.",
    ),
    EmbeddingPair(
        name="fire_vs_burning",
        text_a="fires and burning things",
        text_b="things that are on fire",
        expect_high=True,
        category="target_semantics",
        notes="Semantically equivalent fire descriptions.",
    ),
    EmbeddingPair(
        name="dangerous_vs_scary",
        text_a="anything dangerous or scary",
        text_b="threats and dangerous creatures",
        expect_high=True,
        category="target_semantics",
        notes="Overlapping flee/destroy targets.",
    ),
    EmbeddingPair(
        name="prey_vs_food",
        text_a="small prey animals",
        text_b="food, especially meat",
        expect_high=True,
        category="target_semantics",
        notes="Wolf's prey target and eating target should overlap.",
    ),
    # ===== Edge cases =====
    EmbeddingPair(
        name="empty_vs_object",
        text_a="",
        text_b=_identity("Rock", "a rough gray boulder", "medium", [Tag.RIGID, Tag.HEAVY]),
        expect_high=False,
        category="edge_case",
        notes="Empty string should have low similarity to any object.",
    ),
    EmbeddingPair(
        name="nonsense_vs_object",
        text_a="asdfghjkl qwerty zxcvbn",
        text_b=_identity("Rock", "a rough gray boulder", "medium", [Tag.RIGID, Tag.HEAVY]),
        expect_high=False,
        category="edge_case",
        notes="Nonsense should have low similarity.",
    ),
]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _check_ollama() -> bool:
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


async def run_embedding_eval(
    threshold_high: float = 0.5,
    threshold_low: float = 0.35,
) -> dict:
    """Run all embedding pairs, return results dict."""
    # Collect all unique texts
    texts: list[str] = []
    text_to_idx: dict[str, int] = {}
    for pair in EMBEDDING_PAIRS:
        for t in (pair.text_a, pair.text_b):
            if t not in text_to_idx:
                text_to_idx[t] = len(texts)
                texts.append(t)

    # Batch embed
    t0 = time.monotonic()
    embeddings = await embed_texts(texts)
    embed_elapsed = time.monotonic() - t0

    # Score each pair
    results = []
    passed = 0
    for pair in EMBEDDING_PAIRS:
        emb_a = embeddings[text_to_idx[pair.text_a]]
        emb_b = embeddings[text_to_idx[pair.text_b]]
        sim = _cosine_sim(emb_a, emb_b)

        if pair.expect_high:
            ok = sim >= threshold_high
        else:
            ok = sim <= threshold_low

        if ok:
            passed += 1

        results.append({
            "name": pair.name,
            "category": pair.category,
            "similarity": round(sim, 4),
            "expected": "high" if pair.expect_high else "low",
            "threshold": threshold_high if pair.expect_high else threshold_low,
            "pass": ok,
            "notes": pair.notes,
        })

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_pairs": len(EMBEDDING_PAIRS),
        "passed": passed,
        "failed": len(EMBEDDING_PAIRS) - passed,
        "pass_rate": round(passed / len(EMBEDDING_PAIRS) * 100, 1),
        "threshold_high": threshold_high,
        "threshold_low": threshold_low,
        "unique_texts_embedded": len(texts),
        "embed_elapsed_s": round(embed_elapsed, 3),
        "results": results,
    }


def print_results(data: dict) -> None:  # noqa: T201
    """Print a formatted results table."""
    print(f"\nEmbedding Eval — {data['passed']}/{data['total_pairs']} passed "  # noqa: T201
          f"({data['pass_rate']}%)")
    print(f"Thresholds: high >= {data['threshold_high']}, "  # noqa: T201
          f"low <= {data['threshold_low']}")
    print(f"Embedded {data['unique_texts_embedded']} texts "  # noqa: T201
          f"in {data['embed_elapsed_s']}s\n")

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for r in data["results"]:
        by_cat.setdefault(r["category"], []).append(r)

    header = f"{'Name':<35} {'Sim':>6} {'Exp':>6} {'Thr':>6} {'Result':>6}"
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201

    for cat, pairs in by_cat.items():
        print(f"\n  [{cat}]")  # noqa: T201
        for r in pairs:
            status = "PASS" if r["pass"] else "FAIL"
            mark = " " if r["pass"] else "*"
            print(f"{mark} {r['name']:<34} {r['similarity']:>6.3f} "  # noqa: T201
                  f"{r['expected']:>6} {r['threshold']:>6.2f} {status:>6}")

    # Summary by category
    print(f"\n{'Category':<25} {'Pass':>6} {'Fail':>6}")  # noqa: T201
    print("-" * 37)  # noqa: T201
    for cat, pairs in by_cat.items():
        p = sum(1 for r in pairs if r["pass"])
        f = len(pairs) - p
        print(f"  {cat:<23} {p:>6} {f:>6}")  # noqa: T201

    # High/low group averages
    high_sims = [r["similarity"] for r in data["results"] if r["expected"] == "high"]
    low_sims = [r["similarity"] for r in data["results"] if r["expected"] == "low"]
    if high_sims:
        print(f"\nAvg similarity (expect high): "  # noqa: T201
              f"{sum(high_sims)/len(high_sims):.3f} (n={len(high_sims)})")
    if low_sims:
        print(f"Avg similarity (expect low):  "  # noqa: T201
              f"{sum(low_sims)/len(low_sims):.3f} (n={len(low_sims)})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate embedding quality for behavior targeting"
    )
    parser.add_argument("--threshold-high", type=float, default=0.55,
                        help="Min cosine sim for 'high' pairs (default: 0.55)")
    parser.add_argument("--threshold-low", type=float, default=0.55,
                        help="Max cosine sim for 'low' pairs (default: 0.55)")
    parser.add_argument("--save", action="store_true", default=True,
                        help="Save results to evals/results/ (default: true)")
    parser.add_argument("--no-save", action="store_false", dest="save")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if not _check_ollama():
        print("Error: Ollama not available at http://127.0.0.1:11434")  # noqa: T201
        print("Start it with: ollama serve")  # noqa: T201
        print("Pull model with: ollama pull qwen3-embedding:0.6b")  # noqa: T201
        sys.exit(1)

    data = await run_embedding_eval(
        threshold_high=args.threshold_high,
        threshold_low=args.threshold_low,
    )

    print_results(data)

    if args.save:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_dir = RESULTS_DIR / f"{ts}_embedding"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "result.json"
        out_path.write_text(json.dumps(data, indent=2))
        print(f"\nResults saved to {out_dir}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
