"""Comprehensive test: freeform category embeddings on qwen3-embedding:4b.

Tests whether LLM-assigned freeform categories + 4b embedding model
can reliably match behavior targets without any tag involvement.
"""

import asyncio
import math
import time

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen3-embedding:4b"


async def embed(texts):
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed", json={"model": MODEL, "input": texts}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0


async def test():
    # =================================================================
    # 40 objects with freeform categories (what an LLM would assign)
    # =================================================================
    objects = {
        # Food / consumables
        "Donut":            ["food", "pastry", "snack"],
        "Sandwich":         ["food", "bread", "meal"],
        "Apple":            ["food", "fruit"],
        "Health Potion":    ["potion", "medicine", "drink"],
        "Beer":             ["drink", "alcohol", "beverage"],
        "Poison Mushroom":  ["mushroom", "poison", "plant"],
        # Creatures
        "Wolf":             ["animal", "predator", "beast"],
        "Friendly Dog":     ["animal", "pet", "dog"],
        "Acid Spider":      ["insect", "spider", "venomous creature"],
        "Dragon":           ["monster", "dragon", "beast"],
        "Ghost":            ["spirit", "undead", "supernatural"],
        "Villager":         ["person", "civilian", "peasant"],
        "Robber":           ["criminal", "person", "thief"],
        "Cop":              ["person", "law enforcement", "officer"],
        "Brave Knight":     ["warrior", "person", "knight"],
        "Danger Noodle":    ["snake", "reptile", "animal"],
        "Pegasus":          ["horse", "mythical creature", "animal"],
        "Cowardly Slime":   ["slime", "creature", "blob"],
        "Cyborg T-Rex":     ["dinosaur", "robot", "monster"],
        "Pack Mule":        ["animal", "horse", "pack animal"],
        # Weapons
        "Fire Sword":       ["weapon", "sword", "blade"],
        "Greatsword":       ["weapon", "sword", "blade"],
        "Dagger":           ["weapon", "knife", "blade"],
        "Bow":              ["weapon", "ranged weapon", "bow"],
        # Nature / environment
        "Oak Tree":         ["plant", "tree", "wood"],
        "Rock":             ["stone", "rock", "mineral"],
        "Campfire":         ["fire", "heat source", "flame"],
        "Ice Wall":         ["wall", "barrier", "ice"],
        "Puddle":           ["water", "puddle", "liquid"],
        "Tornado":          ["wind", "storm", "weather"],
        # Utility / misc
        "Treasure Chest":   ["container", "chest", "treasure"],
        "Rubber Duck":      ["toy", "duck", "bath toy"],
        "Wooden Chair":     ["furniture", "chair", "wood"],
        "Glass Bottle":     ["container", "bottle", "glass"],
        "Rope":             ["tool", "rope", "climbing gear"],
        "Trampoline":       ["toy", "bouncy platform", "spring"],
        "Explosive Barrel":  ["barrel", "explosive", "container"],
        "Bear Trap":        ["trap", "metal device", "weapon"],
        "Magnet":           ["tool", "magnet", "metal device"],
        "Umbrella":         ["tool", "umbrella", "rain gear"],
    }

    # =================================================================
    # 20 behavior targets (freeform text from LLM)
    # =================================================================
    behavior_targets = {
        "food, especially donuts": {
            "true": ["Donut", "Sandwich", "Apple"],
            "false": ["Rock", "Wolf", "Treasure Chest", "Rope", "Fire Sword"],
        },
        "criminals and lawbreakers": {
            "true": ["Robber"],
            "false": ["Villager", "Cop", "Donut", "Wolf", "Brave Knight"],
        },
        "prey animals": {
            "true": ["Villager", "Friendly Dog", "Danger Noodle", "Pack Mule"],
            "false": ["Rock", "Fire Sword", "Campfire", "Treasure Chest", "Oak Tree"],
        },
        "enemies and monsters": {
            "true": ["Dragon", "Wolf", "Acid Spider", "Ghost", "Cyborg T-Rex"],
            "false": ["Donut", "Villager", "Rock", "Oak Tree", "Rubber Duck"],
        },
        "small insects and bugs": {
            "true": ["Acid Spider"],
            "false": ["Wolf", "Dragon", "Rock", "Villager", "Oak Tree"],
        },
        "fire and burning things": {
            "true": ["Campfire"],
            "false": ["Rock", "Wolf", "Donut", "Ice Wall", "Puddle"],
        },
        "innocent people": {
            "true": ["Villager"],
            "false": ["Robber", "Wolf", "Dragon", "Rock", "Donut"],
        },
        "anything dangerous or scary": {
            "true": ["Dragon", "Wolf", "Acid Spider", "Ghost", "Danger Noodle"],
            "false": ["Donut", "Villager", "Rock", "Rubber Duck", "Apple"],
        },
        "other creatures": {
            "true": ["Wolf", "Friendly Dog", "Dragon", "Villager", "Acid Spider"],
            "false": ["Rock", "Fire Sword", "Oak Tree", "Campfire", "Puddle"],
        },
        "interesting nearby objects": {
            "true": ["Treasure Chest", "Rubber Duck", "Glass Bottle", "Campfire"],
            "false": ["Rock"],
        },
        "weapons and sharp things": {
            "true": ["Fire Sword", "Greatsword", "Dagger", "Bear Trap"],
            "false": ["Donut", "Villager", "Puddle", "Rubber Duck", "Rope"],
        },
        "treasure and valuables": {
            "true": ["Treasure Chest"],
            "false": ["Rock", "Rope", "Puddle", "Wolf", "Oak Tree"],
        },
        "supernatural monsters": {
            "true": ["Ghost", "Dragon"],
            "false": ["Villager", "Donut", "Rock", "Wolf", "Friendly Dog"],
        },
        "plants and vegetation": {
            "true": ["Oak Tree", "Poison Mushroom"],
            "false": ["Rock", "Wolf", "Donut", "Fire Sword", "Villager"],
        },
        "things to drink": {
            "true": ["Health Potion", "Beer", "Puddle"],
            "false": ["Rock", "Fire Sword", "Wolf", "Oak Tree", "Donut"],
        },
        "explosives and bombs": {
            "true": ["Explosive Barrel"],
            "false": ["Rock", "Donut", "Wolf", "Oak Tree", "Villager"],
        },
        "furniture": {
            "true": ["Wooden Chair"],
            "false": ["Rock", "Wolf", "Donut", "Fire Sword", "Villager"],
        },
        "horses and mounts": {
            "true": ["Pegasus", "Pack Mule"],
            "false": ["Wolf", "Villager", "Rock", "Donut", "Dragon"],
        },
        "reptiles and snakes": {
            "true": ["Danger Noodle"],
            "false": ["Wolf", "Friendly Dog", "Villager", "Rock", "Acid Spider"],
        },
        "traps and hazards": {
            "true": ["Bear Trap", "Explosive Barrel"],
            "false": ["Donut", "Villager", "Rock", "Rubber Duck", "Friendly Dog"],
        },
    }

    # =================================================================
    # Embed everything
    # =================================================================
    all_texts = []
    text_idx = {}

    for cats in objects.values():
        for cat in cats:
            if cat not in text_idx:
                text_idx[cat] = len(all_texts)
                all_texts.append(cat)

    for target in behavior_targets:
        if target not in text_idx:
            text_idx[target] = len(all_texts)
            all_texts.append(target)

    print(f"Embedding {len(all_texts)} unique texts with {MODEL}...")
    t0 = time.monotonic()
    vecs = await embed(all_texts)
    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s. Dims: {len(vecs[0])}")

    # =================================================================
    # Score every target
    # =================================================================
    def best_score(obj_name, target):
        tv = vecs[text_idx[target]]
        cats = objects[obj_name]
        scores = [(c, _cos(tv, vecs[text_idx[c]])) for c in cats]
        best = max(scores, key=lambda x: x[1])
        return best[1], best[0]

    print(f"\n{'=' * 75}")
    print(f"RESULTS: {len(behavior_targets)} behavior targets x {len(objects)} objects")
    print(f"{'=' * 75}")

    all_gaps = []
    failures = []

    for target, match_info in behavior_targets.items():
        true_objs = match_info["true"]
        false_objs = match_info["false"]

        true_scores = [(o, *best_score(o, target)) for o in true_objs]
        false_scores = [(o, *best_score(o, target)) for o in false_objs]

        min_true = min(s for _, s, _ in true_scores)
        max_false = max(s for _, s, _ in false_scores)
        gap = min_true - max_false

        all_gaps.append(gap)

        if gap > 0.08:
            status = "  OK "
        elif gap > 0.03:
            status = "TIGHT"
        elif gap > 0:
            status = " THIN"
        else:
            status = "*FAIL"
            failures.append(target)

        print(f"\n[{status}] \"{target}\"  (gap={gap:+.3f})")
        for o, s, c in sorted(true_scores, key=lambda x: -x[1]):
            print(f"  + {o:<22} {s:.3f}  ({c})")
        top_false = sorted(false_scores, key=lambda x: -x[1])[:3]
        for o, s, c in top_false:
            print(f"  - {o:<22} {s:.3f}  ({c})")

    # =================================================================
    # Summary
    # =================================================================
    separable = sum(1 for g in all_gaps if g > 0)
    clean = sum(1 for g in all_gaps if g > 0.05)
    mean_gap = sum(all_gaps) / len(all_gaps)

    print(f"\n{'=' * 75}")
    print(f"SUMMARY")
    print(f"{'=' * 75}")
    print(f"Total targets:     {len(all_gaps)}")
    print(f"Separable (gap>0): {separable}/{len(all_gaps)}")
    print(f"Clean (gap>0.05):  {clean}/{len(all_gaps)}")
    print(f"Mean gap:          {mean_gap:+.3f}")
    print(f"Min gap:           {min(all_gaps):+.3f}")
    print(f"Max gap:           {max(all_gaps):+.3f}")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")

    # =================================================================
    # Threshold sweep
    # =================================================================
    print(f"\n{'=' * 75}")
    print("THRESHOLD SWEEP")
    print(f"{'=' * 75}")

    for threshold in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        tp = fp = tn = fn = 0
        for target, match_info in behavior_targets.items():
            for obj in match_info["true"]:
                s, _ = best_score(obj, target)
                if s >= threshold:
                    tp += 1
                else:
                    fn += 1
            for obj in match_info["false"]:
                s, _ = best_score(obj, target)
                if s >= threshold:
                    fp += 1
                else:
                    tn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(
            f"  t={threshold:.2f}  "
            f"TP={tp:>3} FP={fp:>3} FN={fn:>3} TN={tn:>3}  "
            f"P={precision:.2f} R={recall:.2f} F1={f1:.2f}"
        )

    # =================================================================
    # Latency test: per-object embed cost
    # =================================================================
    print(f"\n{'=' * 75}")
    print("LATENCY: single object embed (3 categories)")
    print(f"{'=' * 75}")
    times = []
    for _ in range(5):
        t0 = time.monotonic()
        await embed(["food", "pastry", "snack"])
        times.append(time.monotonic() - t0)
    avg = sum(times) / len(times)
    print(f"  5 runs: {[round(t*1000) for t in times]} ms")
    print(f"  Average: {avg*1000:.0f}ms per 3-category embed")


asyncio.run(test())
