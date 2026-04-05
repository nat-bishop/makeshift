"""Test different embedding models and string strategies for identity matching.

The question: is the 0.6b model too weak, or are we building the wrong string?

Strategies tested:
  1. Full string: "Wooden Barrel, a plain oak barrel, medium, made of wood"
  2. Name only: "Wooden Barrel"
  3. Name + substance: "Wooden Barrel, made of wood"
  4. Name + visual: "Wooden Barrel, a plain oak barrel"

Models tested:
  - qwen3-embedding:0.6b (current, 1024-dim)
  - qwen3-embedding:4b (larger, ?-dim)

Only tests pure identity scenarios (where embeddings matter).

Usage:
    cd backend && uv run python -m evals.embedding_strategy_eval
"""

from __future__ import annotations

import asyncio
import math
import sys
import time
from dataclasses import dataclass, field

import httpx


OLLAMA_URL = "http://127.0.0.1:11434"
MODELS = ["qwen3-embedding:0.6b", "qwen3-embedding:4b"]
MATCH_THRESHOLD = 0.5


async def embed_texts_with_model(texts: list[str], model: str) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


SIZE_PHRASES = {"tiny": "tiny", "small": "small", "large": "large", "huge": "towering and huge"}


def strategy_full(name: str, visual: str, size: str, substance: str) -> str:
    parts = [name, visual]
    if size in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


def strategy_name_only(name: str, visual: str, size: str, substance: str) -> str:
    return name


def strategy_name_substance(name: str, visual: str, size: str, substance: str) -> str:
    return f"{name}, made of {substance}"


def strategy_name_visual(name: str, visual: str, size: str, substance: str) -> str:
    return f"{name}, {visual}"


STRATEGIES = {
    "full": strategy_full,
    "name_only": strategy_name_only,
    "name+substance": strategy_name_substance,
    "name+visual": strategy_name_visual,
}


@dataclass
class GameObject:
    name: str
    visual: str
    size: str
    substance: str


@dataclass
class Scenario:
    name: str
    target_text: str
    objects: list[GameObject]
    expected_targets: set[str]


SCENARIOS: list[Scenario] = [
    Scenario(
        name="cop_eats_donuts",
        target_text="food, especially donuts",
        objects=[
            GameObject("Donut", "a glazed sugary donut with rainbow sprinkles", "small", "rubber"),
            GameObject("Pizza", "a hot cheesy pepperoni pizza slice", "small", "cloth"),
            GameObject("Apple", "a shiny red apple", "small", "flesh"),
            GameObject("Steel Sword", "a gleaming sharp blade", "medium", "metal"),
            GameObject("Rock", "a rough gray boulder", "medium", "stone"),
            GameObject("Wooden Table", "a sturdy oak dining table", "large", "wood"),
        ],
        expected_targets={"Donut", "Pizza", "Apple"},
    ),
    Scenario(
        name="mouse_finds_cheese",
        target_text="cheese and small snacks",
        objects=[
            GameObject("Cheese Wheel", "a round yellow wheel of swiss cheese", "small", "rubber"),
            GameObject("Cracker", "a crispy golden cracker", "tiny", "ceramic"),
            GameObject("Iron Helmet", "a heavy iron war helmet", "small", "metal"),
            GameObject("Boulder", "a massive gray rock", "large", "stone"),
            GameObject("Wooden Shield", "a round wooden buckler", "medium", "wood"),
        ],
        expected_targets={"Cheese Wheel", "Cracker"},
    ),
    Scenario(
        name="dragon_hoards_treasure",
        target_text="treasure, gold, and jewels",
        objects=[
            GameObject("Gold Coin", "a shiny gold coin", "tiny", "metal"),
            GameObject("Ruby", "a sparkling red gem", "tiny", "glass"),
            GameObject("Crown", "a golden crown studded with diamonds", "small", "metal"),
            GameObject("Wooden Barrel", "a plain oak barrel", "medium", "wood"),
            GameObject("Villager", "a peasant farmer", "medium", "flesh"),
            GameObject("Iron Sword", "a plain iron longsword", "medium", "metal"),
        ],
        expected_targets={"Gold Coin", "Ruby", "Crown"},
    ),
    Scenario(
        name="bookworm_reads",
        target_text="books, scrolls, and ancient texts",
        objects=[
            GameObject("Ancient Tome", "a dusty leather-bound book with gold clasps", "small",
                       "cloth"),
            GameObject("Magic Scroll", "a rolled parchment with glowing runes", "tiny", "cloth"),
            GameObject("Newspaper", "a folded daily newspaper", "small", "cloth"),
            GameObject("Iron Shield", "a battered round iron shield", "medium", "metal"),
            GameObject("Fire Sword", "a gleaming blade wreathed in flame", "medium", "metal"),
        ],
        expected_targets={"Ancient Tome", "Magic Scroll", "Newspaper"},
    ),
    Scenario(
        name="dog_fetches_balls",
        target_text="balls and toys",
        objects=[
            GameObject("Tennis Ball", "a fuzzy yellow-green tennis ball", "small", "rubber"),
            GameObject("Red Ball", "a shiny red rubber ball", "small", "rubber"),
            GameObject("Frisbee", "a bright orange plastic frisbee", "small", "rubber"),
            GameObject("Bone", "a large white dog bone", "small", "bone"),
            GameObject("Rock", "a dull gray rock", "medium", "stone"),
            GameObject("Villager", "a person walking by", "medium", "flesh"),
        ],
        expected_targets={"Tennis Ball", "Red Ball", "Frisbee"},
    ),
    Scenario(
        name="pirate_seeks_ships",
        target_text="ships and boats",
        objects=[
            GameObject("Wooden Ship", "a large sailing vessel with white sails", "huge", "wood"),
            GameObject("Canoe", "a small wooden canoe", "medium", "wood"),
            GameObject("Raft", "a rough log raft lashed with rope", "medium", "wood"),
            GameObject("Wooden Table", "a sturdy oak dining table", "large", "wood"),
            GameObject("Anchor", "a heavy iron anchor", "medium", "metal"),
            GameObject("Barrel", "a wooden storage barrel", "medium", "wood"),
        ],
        expected_targets={"Wooden Ship", "Canoe", "Raft"},
    ),
    Scenario(
        name="cat_finds_fish",
        target_text="fish and seafood",
        objects=[
            GameObject("Salmon", "a fresh pink salmon fillet", "small", "flesh"),
            GameObject("Goldfish", "a small orange goldfish in a bowl", "tiny", "flesh"),
            GameObject("Crab", "a red crab with large pincers", "small", "flesh"),
            GameObject("Dog", "a friendly brown labrador", "medium", "flesh"),
            GameObject("Rope", "a coiled hemp rope", "small", "cloth"),
        ],
        expected_targets={"Salmon", "Goldfish", "Crab"},
    ),
    Scenario(
        name="wizard_collects_potions",
        target_text="potions and magical elixirs",
        objects=[
            GameObject("Health Potion", "a small glass vial of glowing red liquid", "tiny",
                       "glass"),
            GameObject("Mana Potion", "a blue crystal flask of shimmering liquid", "tiny",
                       "glass"),
            GameObject("Wine Bottle", "a green glass bottle of red wine", "small", "glass"),
            GameObject("Glass Window", "a clear rectangular glass pane", "large", "glass"),
            GameObject("Iron Key", "a rusty old iron skeleton key", "tiny", "metal"),
        ],
        expected_targets={"Health Potion", "Mana Potion"},
    ),
    Scenario(
        name="musician_finds_instruments",
        target_text="musical instruments",
        objects=[
            GameObject("Guitar", "a wooden acoustic guitar with steel strings", "medium", "wood"),
            GameObject("Drum", "a large wooden drum with a leather top", "medium", "wood"),
            GameObject("Flute", "a silver metal flute", "small", "metal"),
            GameObject("Wooden Chair", "a simple wooden chair", "medium", "wood"),
            GameObject("Iron Bell", "a large iron bell", "medium", "metal"),
        ],
        expected_targets={"Guitar", "Drum", "Flute"},
    ),
    Scenario(
        name="gardener_tends_plants",
        target_text="plants and flowers",
        objects=[
            GameObject("Rose Bush", "a thorny bush covered in red roses", "medium", "wood"),
            GameObject("Sunflower", "a tall yellow sunflower", "medium", "wood"),
            GameObject("Cactus", "a prickly green cactus", "medium", "wood"),
            GameObject("Wooden Fence", "a simple wooden picket fence", "medium", "wood"),
            GameObject("Rock", "a smooth river stone", "small", "stone"),
        ],
        expected_targets={"Rose Bush", "Sunflower", "Cactus"},
    ),
]


async def main() -> None:
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception:
        print("Error: Ollama not available")  # noqa: T201
        sys.exit(1)

    # For each model x strategy, collect all texts, embed, score
    results: dict[str, dict[str, list[tuple[str, int, int]]]] = {}
    # results[model][strategy] = [(scenario_name, correct, total), ...]

    for model in MODELS:
        results[model] = {}
        for strat_name, strat_fn in STRATEGIES.items():
            # Collect texts
            texts_map: dict[str, str] = {}
            for sc in SCENARIOS:
                texts_map[f"target:{sc.target_text}"] = sc.target_text
                for obj in sc.objects:
                    key = f"obj:{obj.name}:{strat_name}"
                    texts_map[key] = strat_fn(obj.name, obj.visual, obj.size, obj.substance)

            unique_texts: list[str] = []
            text_to_idx: dict[str, int] = {}
            for text in texts_map.values():
                if text not in text_to_idx:
                    text_to_idx[text] = len(unique_texts)
                    unique_texts.append(text)

            t0 = time.monotonic()
            embeddings = await embed_texts_with_model(unique_texts, model)
            elapsed = time.monotonic() - t0

            cache: dict[str, list[float]] = {}
            for key, text in texts_map.items():
                cache[key] = embeddings[text_to_idx[text]]

            dim = len(embeddings[0]) if embeddings else 0
            print(f"  {model} / {strat_name}: {len(unique_texts)} texts, "  # noqa: T201
                  f"{dim}-dim, {elapsed:.2f}s")

            scenario_results = []
            for sc in SCENARIOS:
                target_emb = cache[f"target:{sc.target_text}"]
                correct = 0
                for obj in sc.objects:
                    obj_emb = cache[f"obj:{obj.name}:{strat_name}"]
                    sim = _cosine_sim(target_emb, obj_emb)
                    targeted = sim >= MATCH_THRESHOLD
                    should = obj.name in sc.expected_targets
                    if targeted == should:
                        correct += 1
                scenario_results.append((sc.name, correct, len(sc.objects)))
            results[model][strat_name] = scenario_results

    # Print detailed results per scenario
    print(f"\n{'=' * 120}")  # noqa: T201
    print("DETAILED RESULTS (threshold = 0.5)")  # noqa: T201
    print(f"{'=' * 120}")  # noqa: T201

    for sc in SCENARIOS:
        print(f"\n--- {sc.name}: \"{sc.target_text}\" ---")  # noqa: T201

        # Print similarity scores for each model x strategy
        for model in MODELS:
            model_short = model.split(":")[1]
            for strat_name, strat_fn in STRATEGIES.items():
                # Re-embed for display (use cached from above, but we need to recompute sims)
                # Actually let's just collect all sims in the first pass
                pass

        # Re-run for detailed output
        for model in MODELS:
            model_short = model.split(":")[1]
            for strat_name, strat_fn in STRATEGIES.items():
                texts_map: dict[str, str] = {}
                texts_map["target"] = sc.target_text
                for obj in sc.objects:
                    texts_map[obj.name] = strat_fn(obj.name, obj.visual, obj.size, obj.substance)

                unique_texts = []
                text_to_idx = {}
                for text in texts_map.values():
                    if text not in text_to_idx:
                        text_to_idx[text] = len(unique_texts)
                        unique_texts.append(text)

                embeddings = await embed_texts_with_model(unique_texts, model)
                cache = {}
                for key, text in texts_map.items():
                    cache[key] = embeddings[text_to_idx[text]]

                target_emb = cache["target"]
                label = f"{model_short}/{strat_name}"
                parts = []
                for obj in sc.objects:
                    sim = _cosine_sim(target_emb, cache[obj.name])
                    should = obj.name in sc.expected_targets
                    targeted = sim >= MATCH_THRESHOLD
                    ok = targeted == should
                    mark = " " if ok else "*"
                    parts.append(f"{mark}{obj.name[:15]:<15} {sim:.3f}")
                print(f"  {label:<25} {' | '.join(parts)}")  # noqa: T201

    # Summary table
    print(f"\n{'=' * 120}")  # noqa: T201
    print("ACCURACY SUMMARY (correct decisions / total objects)")  # noqa: T201
    print(f"{'=' * 120}\n")  # noqa: T201

    header = f"{'Model/Strategy':<30}"
    for sc in SCENARIOS:
        header += f" {sc.name[:12]:>12}"
    header += f" {'TOTAL':>8}"
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201

    for model in MODELS:
        model_short = model.split(":")[1]
        for strat_name in STRATEGIES:
            label = f"{model_short}/{strat_name}"
            row = f"{label:<30}"
            total_correct = 0
            total_objects = 0
            for sc_name, correct, total in results[model][strat_name]:
                row += f" {correct}/{total}".rjust(12)
                total_correct += correct
                total_objects += total
            pct = 100 * total_correct / total_objects if total_objects else 0
            row += f" {total_correct}/{total_objects} ({pct:.0f}%)".rjust(8)
            print(row)  # noqa: T201
        print()  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
