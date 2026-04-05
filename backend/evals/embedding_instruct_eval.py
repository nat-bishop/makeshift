"""Test instruction-prefixed embeddings for better identity matching.

qwen3-embedding supports asymmetric retrieval: queries get task instructions,
documents are embedded raw. We've been doing symmetric (both raw), which isn't
how the model was trained.

Tests:
  A. Raw target vs raw identity (current approach)
  B. Instructed query vs raw identity ("Identify objects that are: <target>")
  C. Classification query vs raw identity ("Is this a type of <target>?")
  D. Retrieval-style query ("Find: <target>") vs raw identity

Also tests both 0.6b and 4b models.

Usage:
    cd backend && uv run python -m evals.embedding_instruct_eval
"""

from __future__ import annotations

import asyncio
import math
import sys
import time
from dataclasses import dataclass

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
MATCH_THRESHOLD = 0.5


async def embed_with_model(texts: list[str], model: str) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


SIZE_PHRASES = {"tiny": "tiny", "small": "small", "large": "large", "huge": "towering and huge"}


def identity_string(name: str, visual: str, size: str, substance: str) -> str:
    parts = [name, visual]
    if size in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


# Query prefix strategies
def raw_query(target: str) -> str:
    return target


def instruct_identify(target: str) -> str:
    return f"Instruct: Identify objects that belong to this category.\nQuery: {target}"


def instruct_classify(target: str) -> str:
    return f"Instruct: Given an object category, retrieve objects that are examples of that category.\nQuery: {target}"


def instruct_retrieve(target: str) -> str:
    return f"Instruct: Retrieve objects matching this description.\nQuery: {target}"


def instruct_yesno(target: str) -> str:
    return f"Instruct: Determine if an object belongs to the category described below.\nQuery: {target}"


def instruct_search(target: str) -> str:
    return f"Instruct: Given a search query about object types, retrieve relevant game objects.\nQuery: {target}"


QUERY_STRATEGIES = {
    "raw": raw_query,
    "identify": instruct_identify,
    "classify": instruct_classify,
    "retrieve": instruct_retrieve,
    "yesno": instruct_yesno,
    "search": instruct_search,
}


@dataclass
class Obj:
    name: str
    visual: str
    size: str
    substance: str
    is_target: bool


@dataclass
class Scenario:
    name: str
    target: str
    objects: list[Obj]


SCENARIOS = [
    Scenario("cop_donuts", "food, especially donuts", [
        Obj("Donut", "a glazed sugary donut with rainbow sprinkles", "small", "rubber", True),
        Obj("Pizza", "a hot cheesy pepperoni pizza slice", "small", "cloth", True),
        Obj("Apple", "a shiny red apple", "small", "flesh", True),
        Obj("Steel Sword", "a gleaming sharp blade", "medium", "metal", False),
        Obj("Rock", "a rough gray boulder", "medium", "stone", False),
        Obj("Wooden Table", "a sturdy oak dining table", "large", "wood", False),
    ]),
    Scenario("dragon_treasure", "treasure, gold, and jewels", [
        Obj("Gold Coin", "a shiny gold coin", "tiny", "metal", True),
        Obj("Ruby", "a sparkling red gem", "tiny", "glass", True),
        Obj("Crown", "a golden crown studded with diamonds", "small", "metal", True),
        Obj("Wooden Barrel", "a plain oak barrel", "medium", "wood", False),
        Obj("Villager", "a peasant farmer", "medium", "flesh", False),
        Obj("Iron Sword", "a plain iron longsword", "medium", "metal", False),
    ]),
    Scenario("dog_balls", "balls and toys", [
        Obj("Tennis Ball", "a fuzzy yellow-green tennis ball", "small", "rubber", True),
        Obj("Red Ball", "a shiny red rubber ball", "small", "rubber", True),
        Obj("Frisbee", "a bright orange plastic frisbee", "small", "rubber", True),
        Obj("Bone", "a large white dog bone", "small", "bone", False),
        Obj("Rock", "a dull gray rock", "medium", "stone", False),
        Obj("Villager", "a person walking by", "medium", "flesh", False),
    ]),
    Scenario("bookworm", "books, scrolls, and ancient texts", [
        Obj("Ancient Tome", "a dusty leather-bound book with gold clasps", "small", "cloth", True),
        Obj("Magic Scroll", "a rolled parchment with glowing runes", "tiny", "cloth", True),
        Obj("Newspaper", "a folded daily newspaper", "small", "cloth", True),
        Obj("Iron Shield", "a battered round iron shield", "medium", "metal", False),
        Obj("Fire Sword", "a gleaming blade wreathed in flame", "medium", "metal", False),
    ]),
    Scenario("pirate_ships", "ships and boats", [
        Obj("Wooden Ship", "a large sailing vessel with white sails", "huge", "wood", True),
        Obj("Canoe", "a small wooden canoe", "medium", "wood", True),
        Obj("Raft", "a rough log raft lashed with rope", "medium", "wood", True),
        Obj("Wooden Table", "a sturdy oak dining table", "large", "wood", False),
        Obj("Anchor", "a heavy iron anchor", "medium", "metal", False),
        Obj("Barrel", "a wooden storage barrel", "medium", "wood", False),
    ]),
    Scenario("cat_fish", "fish and seafood", [
        Obj("Salmon", "a fresh pink salmon fillet", "small", "flesh", True),
        Obj("Goldfish", "a small orange goldfish in a bowl", "tiny", "flesh", True),
        Obj("Crab", "a red crab with large pincers", "small", "flesh", True),
        Obj("Dog", "a friendly brown labrador", "medium", "flesh", False),
        Obj("Rope", "a coiled hemp rope", "small", "cloth", False),
    ]),
    Scenario("wizard_potions", "potions and magical elixirs", [
        Obj("Health Potion", "a small glass vial of glowing red liquid", "tiny", "glass", True),
        Obj("Mana Potion", "a blue crystal flask of shimmering liquid", "tiny", "glass", True),
        Obj("Wine Bottle", "a green glass bottle of red wine", "small", "glass", False),
        Obj("Glass Window", "a clear rectangular glass pane", "large", "glass", False),
        Obj("Iron Key", "a rusty old iron skeleton key", "tiny", "metal", False),
    ]),
    Scenario("gardener_plants", "plants and flowers", [
        Obj("Rose Bush", "a thorny bush covered in red roses", "medium", "wood", True),
        Obj("Sunflower", "a tall yellow sunflower", "medium", "wood", True),
        Obj("Cactus", "a prickly green cactus", "medium", "wood", True),
        Obj("Wooden Fence", "a simple wooden picket fence", "medium", "wood", False),
        Obj("Rock", "a smooth river stone", "small", "stone", False),
    ]),
    Scenario("musician_instruments", "musical instruments", [
        Obj("Guitar", "a wooden acoustic guitar with steel strings", "medium", "wood", True),
        Obj("Drum", "a large wooden drum with a leather top", "medium", "wood", True),
        Obj("Flute", "a silver metal flute", "small", "metal", True),
        Obj("Wooden Chair", "a simple wooden chair", "medium", "wood", False),
        Obj("Iron Bell", "a large iron bell", "medium", "metal", False),
    ]),
    Scenario("wolf_prey", "small prey animals", [
        Obj("Rabbit", "a small fluffy brown rabbit", "small", "flesh", True),
        Obj("Chicken", "a plump white chicken", "small", "flesh", True),
        Obj("Mouse", "a tiny gray field mouse", "tiny", "flesh", True),
        Obj("Bear", "a massive brown grizzly bear", "large", "flesh", False),
        Obj("Oak Tree", "a tall green oak tree", "large", "wood", False),
    ]),
]


async def main() -> None:
    try:
        httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).raise_for_status()
    except Exception:
        print("Ollama not available")  # noqa: T201
        sys.exit(1)

    models = ["qwen3-embedding:0.6b", "qwen3-embedding:4b"]

    # Build all identity strings (same across all strategies)
    obj_texts: dict[str, str] = {}
    for sc in SCENARIOS:
        for obj in sc.objects:
            key = f"{sc.name}:{obj.name}"
            obj_texts[key] = identity_string(obj.name, obj.visual, obj.size, obj.substance)

    # For each model x strategy, embed and score
    all_results: dict[str, dict[str, list[tuple[str, int, int, float]]]] = {}
    # all_results[model][strategy] = [(scenario, correct, total, avg_gap), ...]
    all_id_caches: dict[str, dict[str, list[float]]] = {}

    for model in models:
        model_short = model.split(":")[1]
        all_results[model] = {}

        # Embed all identity strings once per model
        id_unique: list[str] = []
        id_idx: dict[str, int] = {}
        for text in obj_texts.values():
            if text not in id_idx:
                id_idx[text] = len(id_unique)
                id_unique.append(text)

        print(f"Embedding {len(id_unique)} identity texts with {model}...", end=" ")  # noqa: T201
        t0 = time.monotonic()
        id_embeddings = await embed_with_model(id_unique, model)
        print(f"{time.monotonic()-t0:.1f}s")  # noqa: T201

        id_cache: dict[str, list[float]] = {}
        for key, text in obj_texts.items():
            id_cache[key] = id_embeddings[id_idx[text]]
        all_id_caches[model] = id_cache

        for strat_name, strat_fn in QUERY_STRATEGIES.items():
            # Embed all query texts for this strategy
            q_texts: list[str] = []
            q_idx: dict[str, int] = {}
            for sc in SCENARIOS:
                qt = strat_fn(sc.target)
                if qt not in q_idx:
                    q_idx[qt] = len(q_texts)
                    q_texts.append(qt)

            q_embeddings = await embed_with_model(q_texts, model)
            q_cache: dict[str, list[float]] = {}
            for sc in SCENARIOS:
                qt = strat_fn(sc.target)
                q_cache[sc.name] = q_embeddings[q_idx[qt]]

            scenario_results = []
            for sc in SCENARIOS:
                q_emb = q_cache[sc.name]
                correct = 0
                target_sims = []
                non_target_sims = []

                for obj in sc.objects:
                    key = f"{sc.name}:{obj.name}"
                    sim = cosine_sim(q_emb, id_cache[key])
                    targeted = sim >= MATCH_THRESHOLD
                    if targeted == obj.is_target:
                        correct += 1
                    if obj.is_target:
                        target_sims.append(sim)
                    else:
                        non_target_sims.append(sim)

                # Gap = avg target sim - avg non-target sim (bigger = better discrimination)
                avg_target = sum(target_sims) / len(target_sims) if target_sims else 0
                avg_non = sum(non_target_sims) / len(non_target_sims) if non_target_sims else 0
                gap = avg_target - avg_non

                scenario_results.append((sc.name, correct, len(sc.objects), gap))
            all_results[model][strat_name] = scenario_results

    # Print detailed per-scenario output for best strategies
    print(f"\n{'='*110}")  # noqa: T201
    print("SIMILARITY SCORES — best strategies per model")  # noqa: T201
    print(f"{'='*110}")  # noqa: T201

    # Pick top 3 strategies per model by total accuracy
    for model in models:
        model_short = model.split(":")[1]
        id_cache = all_id_caches[model]
        strat_totals = {}
        for strat_name, sr in all_results[model].items():
            strat_totals[strat_name] = sum(c for _, c, _, _ in sr)
        top_strats = sorted(strat_totals, key=strat_totals.get, reverse=True)[:3]

        for strat_name in top_strats:
            strat_fn = QUERY_STRATEGIES[strat_name]
            print(f"\n--- {model_short} / {strat_name} ---")  # noqa: T201

            # Re-embed queries for display
            for sc in SCENARIOS:
                qt = strat_fn(sc.target)
                q_embs = await embed_with_model([qt], model)
                q_emb = q_embs[0]

                parts = []
                for obj in sc.objects:
                    key = f"{sc.name}:{obj.name}"
                    sim = cosine_sim(q_emb, id_cache[key])
                    mark = "+" if obj.is_target else "-"
                    ok = (sim >= MATCH_THRESHOLD) == obj.is_target
                    flag = " " if ok else "*"
                    parts.append(f"{flag}{mark}{obj.name[:14]:<14} {sim:.3f}")
                print(f"  {sc.name:<20} \"{sc.target[:30]}\"")  # noqa: T201
                print(f"    {' | '.join(parts)}")  # noqa: T201

    # Summary table
    print(f"\n{'='*110}")  # noqa: T201
    print("ACCURACY + DISCRIMINATION GAP SUMMARY")  # noqa: T201
    print("  Accuracy = correct targeting decisions at threshold 0.5")  # noqa: T201
    print("  Gap = avg(target sims) - avg(non-target sims) — bigger is better")  # noqa: T201
    print(f"{'='*110}\n")  # noqa: T201

    header = f"{'Model/Strategy':<28} {'Accuracy':>10} {'Avg Gap':>10}"
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201

    for model in models:
        model_short = model.split(":")[1]
        strat_rows = []
        for strat_name, sr in all_results[model].items():
            total_correct = sum(c for _, c, _, _ in sr)
            total_objs = sum(t for _, _, t, _ in sr)
            avg_gap = sum(g for _, _, _, g in sr) / len(sr) if sr else 0
            pct = 100 * total_correct / total_objs
            strat_rows.append((strat_name, total_correct, total_objs, pct, avg_gap))

        # Sort by accuracy desc
        strat_rows.sort(key=lambda x: (x[3], x[4]), reverse=True)
        for strat_name, tc, to, pct, gap in strat_rows:
            label = f"{model_short}/{strat_name}"
            print(f"{label:<28} {tc}/{to} ({pct:4.0f}%) {gap:>10.3f}")  # noqa: T201
        print()  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
