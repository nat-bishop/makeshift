"""One-off test: category-based embedding matching viability."""

import asyncio
import math

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"


async def embed(texts, model="qwen3-embedding:0.6b"):
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0


async def test():
    objects = {
        "Donut": ["food", "pastry", "snack"],
        "Sandwich": ["food", "bread", "meal"],
        "Robber": ["criminal", "person", "thief"],
        "Villager": ["person", "civilian", "peasant"],
        "Wolf": ["animal", "predator", "beast"],
        "Oak Tree": ["plant", "tree", "wood"],
        "Fire Sword": ["weapon", "sword", "blade"],
        "Rock": ["stone", "debris", "mineral"],
        "Cop": ["person", "law enforcement", "officer"],
        "Spider": ["insect", "bug", "arachnid"],
        "Danger Noodle": ["snake", "reptile", "animal"],
        "Ghost": ["spirit", "undead", "supernatural"],
        "Dragon": ["monster", "beast", "dragon"],
        "Campfire": ["fire", "heat source", "light"],
        "Healing Mushroom": ["plant", "mushroom", "medicine"],
        "Treasure Chest": ["container", "treasure", "loot"],
        "Acid Spider": ["insect", "arachnid", "venomous creature"],
        "Rubber Duck": ["toy", "duck", "bath toy"],
        "Pegasus": ["animal", "horse", "mythical creature"],
        "Ice Wall": ["wall", "barrier", "ice structure"],
    }

    all_texts = []
    text_idx = {}
    for cats in objects.values():
        for cat in cats:
            if cat not in text_idx:
                text_idx[cat] = len(all_texts)
                all_texts.append(cat)

    targets = [
        "food, especially donuts",
        "criminals and lawbreakers",
        "prey animals",
        "enemies and monsters",
        "small insects and bugs",
        "fire and burning things",
        "innocent people",
        "anything dangerous or scary",
    ]
    for t in targets:
        text_idx[t] = len(all_texts)
        all_texts.append(t)

    vecs = await embed(all_texts)

    def best_match(obj_name, target):
        tv = vecs[text_idx[target]]
        cats = objects[obj_name]
        scores = [(c, _cos(tv, vecs[text_idx[c]])) for c in cats]
        best = max(scores, key=lambda x: x[1])
        return best[1], best[0]

    # =================================================================
    # THRESHOLD ANALYSIS
    # =================================================================
    print("=" * 70)
    print("THRESHOLD ANALYSIS: can we separate true from false matches?")
    print("=" * 70)

    test_cases = [
        (
            "food, especially donuts",
            ["Donut", "Sandwich", "Healing Mushroom"],
            ["Robber", "Rock", "Fire Sword", "Wolf", "Treasure Chest", "Villager"],
        ),
        (
            "criminals and lawbreakers",
            ["Robber"],
            ["Villager", "Donut", "Wolf", "Oak Tree", "Cop"],
        ),
        (
            "prey animals",
            ["Villager", "Danger Noodle", "Pegasus", "Rubber Duck"],
            ["Rock", "Fire Sword", "Oak Tree", "Campfire"],
        ),
        (
            "enemies and monsters",
            ["Dragon", "Wolf", "Acid Spider", "Ghost"],
            ["Donut", "Rock", "Villager", "Oak Tree"],
        ),
        (
            "fire and burning things",
            ["Campfire"],
            ["Rock", "Villager", "Donut", "Wolf", "Oak Tree"],
        ),
        (
            "innocent people",
            ["Villager"],
            ["Robber", "Wolf", "Dragon", "Rock", "Donut"],
        ),
        (
            "anything dangerous or scary",
            ["Dragon", "Wolf", "Acid Spider", "Ghost", "Danger Noodle"],
            ["Donut", "Rock", "Villager", "Oak Tree", "Treasure Chest"],
        ),
        (
            "small insects and bugs",
            ["Spider", "Acid Spider"],
            ["Wolf", "Donut", "Rock", "Villager", "Dragon"],
        ),
    ]

    all_gaps = []
    for target, true_objs, false_objs in test_cases:
        true_scores = [(o, best_match(o, target)[0]) for o in true_objs]
        false_scores = [(o, best_match(o, target)[0]) for o in false_objs]

        min_true = min(s for _, s in true_scores)
        max_false = max(s for _, s in false_scores)
        gap = min_true - max_false
        all_gaps.append(gap)

        status = "OK" if gap > 0.05 else "TIGHT" if gap > 0 else "FAIL"

        print(f"\n[{status:>5}] \"{target}\"")
        for o, s in sorted(true_scores, key=lambda x: -x[1]):
            _, cat = best_match(o, target)
            print(f"        TRUE  {o:<20} {s:.3f}  ({cat})")
        for o, s in sorted(false_scores, key=lambda x: -x[1])[:3]:
            _, cat = best_match(o, target)
            print(f"        false {o:<20} {s:.3f}  ({cat})")
        print(
            f"        Gap: {gap:+.3f}  "
            f"(min_true={min_true:.3f} max_false={max_false:.3f})"
        )

    separable = sum(1 for g in all_gaps if g > 0)
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {separable}/{len(all_gaps)} separable")
    print(f"Mean gap: {sum(all_gaps) / len(all_gaps):+.3f}")
    print(f"Min gap:  {min(all_gaps):+.3f}")

    # =================================================================
    # KEY SCENARIOS
    # =================================================================
    print(f"\n{'=' * 70}")
    print("SCENARIO: Wolf eat -> 'prey animals' + Medusa petrifies villager")
    print("=" * 70)
    v_sim, v_cat = best_match("Villager", "prey animals")
    print(f"  Villager {objects['Villager']} vs 'prey animals': {v_sim:.3f} ({v_cat})")
    print(f"  Wolf eat has required_tags=[LIVING]")
    print(f"  Before: LIVING present  -> semantic pass + tag pass  -> TARGET")
    print(f"  After:  LIVING removed  -> semantic pass + tag FAIL  -> DROPPED")
    print(f"  No re-embedding. Instant boolean check.")

    print(f"\n{'=' * 70}")
    print("SCENARIO: Cop eat -> 'food, especially donuts'")
    print("=" * 70)
    d_sim, _ = best_match("Donut", "food, especially donuts")
    s_sim, _ = best_match("Sandwich", "food, especially donuts")
    r_sim, _ = best_match("Rock", "food, especially donuts")
    print(f"  Donut    {str(objects['Donut']):<30} -> {d_sim:.3f}  MATCH")
    print(f"  Sandwich {str(objects['Sandwich']):<30} -> {s_sim:.3f}  MATCH")
    print(f"  Rock     {str(objects['Rock']):<30} -> {r_sim:.3f}  no match")
    print(f"  Both food items match. Cop goes for nearest.")

    print(f"\n{'=' * 70}")
    print("SCENARIO: Firefighter destroy -> 'fire and burning things'")
    print("=" * 70)
    c_sim, c_cat = best_match("Campfire", "fire and burning things")
    t_sim, t_cat = best_match("Oak Tree", "fire and burning things")
    print(f"  Campfire  {str(objects['Campfire']):<30} -> {c_sim:.3f}  ({c_cat})")
    print(f"  Oak Tree  {str(objects['Oak Tree']):<30} -> {t_sim:.3f}  ({t_cat})")
    print(f"  Tree categories are static - they never say 'fire'.")
    print(f"  Option A: firefighter uses required_tags=[HEAT_SOURCE] ONLY,")
    print(f"            no semantic match needed. Targets anything on fire.")
    print(f"  Option B: tag filter is primary. Semantic narrows further")
    print(f"            (e.g. firefighter ignores a fire sword that has HEAT_SOURCE")
    print(f"             because 'weapon' doesnt match 'fire and burning things').")


asyncio.run(test())
