"""Test: can embeddings reliably answer "is this the kind of thing I want?"

No tag filters. Pure identity matching.
Object = name + visual description (what the LLM outputs).
Target = freeform behavior text.

The question: at what threshold can we separate true targets from non-targets?
"""

import asyncio
import math
import time

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"


async def embed(texts, model):
    async with httpx.AsyncClient(timeout=120.0) as client:
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


# All objects in the scene — name + visual (what the LLM already produces)
OBJECTS = {
    "Donut": "Donut, a glazed sugary donut with rainbow sprinkles",
    "Pizza": "Pizza, a hot cheesy pepperoni pizza slice",
    "Sandwich": "Sandwich, a thick deli sandwich with lettuce and ham",
    "Apple": "Apple, a shiny red apple",
    "Robber": "Robber, a masked criminal in dark clothes with a bag of loot",
    "Villager": "Villager, a frightened peasant in brown clothes",
    "Cop": "Officer Johnson, a stern police officer in blue uniform",
    "Knight": "Brave Knight, a stalwart warrior in dented silver armor",
    "Wolf": "Wolf, a gray wolf with sharp teeth and yellow eyes",
    "Dog": "Friendly Dog, a happy brown dog with a wagging tail",
    "Dragon": "Fire Dragon, a massive red dragon with smoking nostrils",
    "Ghost": "Ghost, a translucent floating specter with hollow eyes",
    "Cthulhu": "Cthulhu, a towering eldritch horror with tentacles and wings",
    "Spider": "Acid Spider, a glossy black spider dripping green acid",
    "Rabbit": "Rabbit, a small fluffy brown rabbit",
    "Snake": "Danger Noodle, a large green snake coiled and hissing",
    "Campfire": "Campfire, crackling orange flames over charred logs",
    "Rock": "Rock, a rough gray boulder with moss patches",
    "Sword": "Fire Sword, a gleaming steel blade wreathed in flame",
    "Treasure": "Treasure Chest, an ornate wooden chest with gold trim",
    "Tree": "Oak Tree, a tall tree with green leaves and thick bark",
    "Rubber Duck": "Rubber Duck, a cheerful yellow rubber duck",
    "Chair": "Wooden Chair, a simple oak chair with four legs",
    "Potion": "Health Potion, a glowing green bottle of healing liquid",
}

# Behavior scenarios: what a creature is looking for
# true = objects that SHOULD match, false = objects that should NOT
SCENARIOS = {
    "cop_eat": {
        "target": "food, especially donuts",
        "true": ["Donut", "Pizza", "Sandwich", "Apple"],
        "false": ["Robber", "Rock", "Sword", "Wolf", "Tree", "Chair", "Treasure"],
    },
    "cop_destroy": {
        "target": "criminals and lawbreakers",
        "true": ["Robber"],
        "false": ["Villager", "Cop", "Knight", "Donut", "Wolf", "Dog", "Rock"],
    },
    "cop_flee": {
        "target": "supernatural horrors and monsters",
        "true": ["Cthulhu", "Ghost", "Dragon"],
        "false": ["Villager", "Donut", "Rock", "Dog", "Rabbit", "Chair"],
    },
    "wolf_eat": {
        "target": "small prey animals",
        "true": ["Rabbit", "Dog", "Snake"],
        "false": ["Rock", "Sword", "Tree", "Campfire", "Chair", "Treasure"],
    },
    "wolf_flee": {
        "target": "fire and flames",
        "true": ["Campfire", "Sword"],
        "false": ["Rock", "Villager", "Donut", "Chair", "Rabbit", "Tree"],
    },
    "knight_destroy": {
        "target": "monsters and evil creatures",
        "true": ["Dragon", "Cthulhu", "Ghost", "Spider"],
        "false": ["Villager", "Donut", "Rock", "Dog", "Rabbit", "Chair"],
    },
    "knight_protect": {
        "target": "innocent villagers and civilians",
        "true": ["Villager"],
        "false": ["Robber", "Wolf", "Dragon", "Rock", "Sword", "Donut"],
    },
    "dragon_destroy": {
        "target": "knights and warriors",
        "true": ["Knight", "Cop"],
        "false": ["Villager", "Donut", "Rabbit", "Rock", "Tree", "Dog"],
    },
    "dog_follow": {
        "target": "people and humans",
        "true": ["Villager", "Robber", "Cop", "Knight"],
        "false": ["Wolf", "Dragon", "Rock", "Tree", "Donut", "Campfire"],
    },
    "rabbit_flee": {
        "target": "predators and large animals",
        "true": ["Wolf", "Dragon", "Snake", "Spider"],
        "false": ["Donut", "Rock", "Chair", "Tree", "Potion", "Treasure"],
    },
    "villager_investigate": {
        "target": "treasure and valuable objects",
        "true": ["Treasure", "Potion"],
        "false": ["Rock", "Chair", "Tree", "Wolf", "Campfire"],
    },
    "thief_steal": {
        "target": "treasure, gold and valuables",
        "true": ["Treasure"],
        "false": ["Rock", "Chair", "Wolf", "Donut", "Tree", "Villager"],
    },
}


async def test():
    for model in ["qwen3-embedding:0.6b", "qwen3-embedding:4b"]:
        # Embed everything
        all_texts = list(OBJECTS.values())
        obj_names = list(OBJECTS.keys())
        target_texts = [s["target"] for s in SCENARIOS.values()]
        all_texts.extend(target_texts)

        t0 = time.monotonic()
        vecs = await embed(all_texts, model)
        elapsed = time.monotonic() - t0

        obj_vecs = {name: vecs[i] for i, name in enumerate(obj_names)}
        target_vecs = {}
        for i, sdata in enumerate(SCENARIOS.values()):
            target_vecs[sdata["target"]] = vecs[len(obj_names) + i]

        print(f"\n{'=' * 80}")
        print(f"MODEL: {model} ({len(vecs[0])} dims, {elapsed:.1f}s)")
        print(f"{'=' * 80}")

        all_gaps = []
        all_true_scores = []
        all_false_scores = []

        for sname, sdata in SCENARIOS.items():
            tv = target_vecs[sdata["target"]]
            trues = [(o, _cos(tv, obj_vecs[o])) for o in sdata["true"]]
            falses = [(o, _cos(tv, obj_vecs[o])) for o in sdata["false"]]

            min_true = min(s for _, s in trues)
            max_false = max(s for _, s in falses)
            gap = min_true - max_false
            all_gaps.append(gap)
            all_true_scores.extend(s for _, s in trues)
            all_false_scores.extend(s for _, s in falses)

            status = "  OK " if gap > 0.05 else "TIGHT" if gap > 0 else "*FAIL"

            print(f"\n[{status}] {sname}: \"{sdata['target']}\"  gap={gap:+.3f}")
            for o, s in sorted(trues, key=lambda x: -x[1]):
                print(f"  + {o:<18} {s:.3f}")
            for o, s in sorted(falses, key=lambda x: -x[1])[:4]:
                print(f"  - {o:<18} {s:.3f}")

        sep = sum(1 for g in all_gaps if g > 0)
        clean = sum(1 for g in all_gaps if g > 0.05)
        print(f"\n--- SUMMARY ({model}) ---")
        print(f"Separable (gap>0): {sep}/{len(all_gaps)}")
        print(f"Clean (gap>0.05):  {clean}/{len(all_gaps)}")
        print(f"Mean gap: {sum(all_gaps)/len(all_gaps):+.3f}")
        print(f"Avg true score:  {sum(all_true_scores)/len(all_true_scores):.3f}")
        print(f"Avg false score: {sum(all_false_scores)/len(all_false_scores):.3f}")

        # Threshold sweep
        print(f"\nThreshold sweep:")
        for t in [0.40, 0.45, 0.50, 0.55, 0.60]:
            tp = fp = tn = fn = 0
            for sdata in SCENARIOS.values():
                tv = target_vecs[sdata["target"]]
                for o in sdata["true"]:
                    if _cos(tv, obj_vecs[o]) >= t:
                        tp += 1
                    else:
                        fn += 1
                for o in sdata["false"]:
                    if _cos(tv, obj_vecs[o]) >= t:
                        fp += 1
                    else:
                        tn += 1
            p = tp / (tp + fp) if (tp + fp) else 0
            r = tp / (tp + fn) if (tp + fn) else 0
            f1 = 2 * p * r / (p + r) if (p + r) else 0
            print(f"  t={t:.2f}  TP={tp:>2} FP={fp:>2} FN={fn:>2} TN={tn:>2}  P={p:.2f} R={r:.2f} F1={f1:.2f}")


asyncio.run(test())
