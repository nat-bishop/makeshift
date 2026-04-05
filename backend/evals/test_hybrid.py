"""Test: freeform embedding (noun) + tag filter (adjective) hybrid system.

Embeddings answer: "what kind of thing is this?" (identity)
Tags answer: "what state is it in?" (condition)

Object identity = name + visual description (static, embedded once at spawn)
Behavior target = freeform text (embedded once at creature spawn)
Tag filter = required_tags on behavior (boolean check, instant)
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
    # Objects: name + visual description (what the LLM already outputs)
    # This is the IDENTITY — what kind of thing is this?
    # Embedded once at spawn. Never changes.
    # =================================================================
    objects = {
        "Donut": "Donut, a glazed sugary donut with rainbow sprinkles",
        "Sandwich": "Sandwich, a thick deli sandwich with lettuce and ham",
        "Apple": "Apple, a shiny red apple",
        "Health Potion": "Health Potion, a glowing green bottle of healing liquid",
        "Robber": "Robber, a masked criminal in dark clothes",
        "Villager": "Villager, a frightened peasant in brown clothes",
        "Cop": "Officer Johnson, a stern police officer in blue uniform",
        "Brave Knight": "Brave Knight, a stalwart warrior in dented silver armor",
        "Wolf": "Wolf, a gray wolf with sharp teeth and yellow eyes",
        "Friendly Dog": "Friendly Dog, a happy brown dog with a wagging tail",
        "Danger Noodle": "Danger Noodle, a large green snake coiled and hissing",
        "Acid Spider": "Acid Spider, a glossy black spider dripping green acid",
        "Dragon": "Fire Dragon, a massive red dragon with smoking nostrils",
        "Ghost": "Ghost, a translucent floating specter with hollow eyes",
        "Pegasus": "Pegasus, a white winged horse glowing with golden light",
        "Cyborg T-Rex": "Cyborg T-Rex, a massive dinosaur with metal plating and laser eye",
        "Cowardly Slime": "Cowardly Slime, a small trembling green blob",
        "Oak Tree": "Oak Tree, a tall tree with green leaves and thick bark",
        "Campfire": "Campfire, crackling flames over charred logs",
        "Rock": "Rock, a rough gray boulder with moss patches",
        "Ice Wall": "Ice Wall, a towering wall of translucent blue ice",
        "Puddle": "Puddle, a small shallow pool of water on the ground",
        "Fire Sword": "Fire Sword, a gleaming steel blade wreathed in flame",
        "Greatsword": "Greatsword, a massive two-handed iron blade",
        "Dagger": "Dagger, a short rusty blade with a leather grip",
        "Treasure Chest": "Treasure Chest, an ornate wooden chest with gold trim",
        "Rubber Duck": "Rubber Duck, a cheerful yellow rubber duck with orange beak",
        "Explosive Barrel": "Explosive Barrel, a wooden barrel marked with danger symbols",
        "Bear Trap": "Bear Trap, a rusty metal jaw trap with sharp teeth",
        "Wooden Chair": "Wooden Chair, a simple oak chair with four legs",
        "Trampoline": "Trampoline, a bouncy fabric platform on a metal frame",
        "Rope": "Rope, a long coil of thick hemp rope",
        "Umbrella": "Umbrella, a small red umbrella with a curved handle",
        "Magnet": "Magnet, a large red horseshoe magnet crackling with energy",
        "Torch": "Torch, a wooden stick wrapped in burning cloth",
        "Healing Mushroom": "Healing Mushroom, a glowing blue mushroom with sparkles",
        "Poison Mushroom": "Poison Mushroom, a sickly purple mushroom oozing green spores",
    }

    # =================================================================
    # Behaviors: freeform target text + required_tags
    # The text answers "what kind of thing?"
    # The tags answer "what state must it be in?"
    # =================================================================
    behaviors = {
        # (target_text, required_tags, true_matches, false_matches)
        # required_tags simulated as a note — the embedding only handles the text part

        "cop_eat": {
            "target": "food, especially donuts",
            "required_tags": [],  # no state requirement for food
            "true": ["Donut", "Sandwich", "Apple"],
            "false": ["Rock", "Wolf", "Treasure Chest", "Fire Sword", "Rope", "Villager"],
        },
        "cop_destroy": {
            "target": "criminals and lawbreakers",
            "required_tags": ["LIVING"],  # must be alive
            "true": ["Robber"],
            "false": ["Villager", "Cop", "Donut", "Wolf", "Brave Knight", "Rock"],
        },
        "cop_flee": {
            "target": "supernatural monsters and ghosts",
            "required_tags": [],
            "true": ["Ghost", "Dragon"],
            "false": ["Wolf", "Villager", "Donut", "Rock", "Friendly Dog"],
        },
        "wolf_eat": {
            "target": "small prey animals and creatures",
            "required_tags": ["LIVING"],  # must be alive (petrified = not prey)
            "true": ["Villager", "Friendly Dog", "Danger Noodle", "Cowardly Slime"],
            "false": ["Rock", "Fire Sword", "Oak Tree", "Campfire", "Treasure Chest"],
        },
        "wolf_flee": {
            "target": "fire and loud noises",
            "required_tags": [],
            "true": ["Campfire", "Torch", "Explosive Barrel"],
            "false": ["Rock", "Villager", "Donut", "Puddle", "Wooden Chair"],
        },
        "knight_destroy": {
            "target": "monsters and evil creatures",
            "required_tags": ["LIVING"],
            "true": ["Dragon", "Acid Spider", "Ghost", "Cyborg T-Rex"],
            "false": ["Villager", "Donut", "Rock", "Friendly Dog", "Rubber Duck"],
        },
        "knight_protect": {
            "target": "innocent villagers and civilians",
            "required_tags": ["LIVING"],
            "true": ["Villager"],
            "false": ["Robber", "Wolf", "Dragon", "Rock", "Donut"],
        },
        "firefighter_destroy": {
            "target": "fires and burning things",
            "required_tags": ["HEAT_SOURCE"],  # KEY: tag filter handles the state
            "true": ["Campfire", "Torch"],
            "false": ["Rock", "Wolf", "Donut", "Oak Tree", "Puddle"],
            # Note: Oak Tree would pass IF it has HEAT_SOURCE tag (on fire)
            # The embedding doesn't need to know about fire state — tags handle it
        },
        "dragon_destroy": {
            "target": "warriors and armed fighters",
            "required_tags": ["LIVING"],
            "true": ["Brave Knight", "Cop"],
            "false": ["Villager", "Donut", "Rock", "Friendly Dog", "Rubber Duck"],
        },
        "spider_eat": {
            "target": "small insects and bugs",
            "required_tags": ["LIVING"],
            "true": ["Acid Spider"],  # only other insect in scene
            "false": ["Wolf", "Dragon", "Rock", "Villager", "Oak Tree"],
        },
        "slime_flee": {
            "target": "anything dangerous or threatening",
            "required_tags": [],
            "true": ["Wolf", "Dragon", "Acid Spider", "Bear Trap", "Fire Sword"],
            "false": ["Donut", "Rubber Duck", "Puddle", "Wooden Chair", "Apple"],
        },
        "villager_investigate": {
            "target": "interesting objects and treasure",
            "required_tags": [],
            "true": ["Treasure Chest", "Rubber Duck", "Healing Mushroom", "Magnet"],
            "false": ["Rock", "Puddle", "Rope"],
        },
        "pegasus_follow": {
            "target": "kind people and gentle creatures",
            "required_tags": ["LIVING"],
            "true": ["Villager", "Friendly Dog"],
            "false": ["Wolf", "Dragon", "Robber", "Rock", "Fire Sword"],
        },
        "dog_follow": {
            "target": "people and humans",
            "required_tags": ["LIVING"],
            "true": ["Villager", "Robber", "Cop", "Brave Knight"],
            "false": ["Wolf", "Dragon", "Rock", "Donut", "Oak Tree"],
        },
    }

    # =================================================================
    # Embed all identity strings and target texts
    # =================================================================
    all_texts = list(objects.values())
    obj_names = list(objects.keys())
    target_texts = [b["target"] for b in behaviors.values()]
    all_texts.extend(target_texts)

    print(f"Embedding {len(all_texts)} texts with {MODEL}...")
    t0 = time.monotonic()
    vecs = await embed(all_texts)
    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s. Dims: {len(vecs[0])}")

    obj_vecs = {name: vecs[i] for i, name in enumerate(obj_names)}
    target_vecs = {
        b["target"]: vecs[len(obj_names) + i]
        for i, b in enumerate(behaviors.values())
    }

    # =================================================================
    # Test each behavior
    # =================================================================
    print(f"\n{'=' * 75}")
    print("HYBRID MATCHING: embedding (noun) + tag filter (adjective)")
    print(f"Model: {MODEL}")
    print(f"{'=' * 75}")

    all_gaps = []
    failures = []

    for bname, bdata in behaviors.items():
        target = bdata["target"]
        req_tags = bdata["required_tags"]
        true_objs = bdata["true"]
        false_objs = bdata["false"]

        tv = target_vecs[target]

        true_scores = [
            (o, _cos(tv, obj_vecs[o])) for o in true_objs
        ]
        false_scores = [
            (o, _cos(tv, obj_vecs[o])) for o in false_objs
        ]

        min_true = min(s for _, s in true_scores)
        max_false = max(s for _, s in false_scores)
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
            failures.append(bname)

        tags_str = f"  req_tags: {req_tags}" if req_tags else ""
        print(f"\n[{status}] {bname}: \"{target}\"{tags_str}  (gap={gap:+.3f})")
        for o, s in sorted(true_scores, key=lambda x: -x[1]):
            print(f"  + {o:<22} {s:.3f}")
        for o, s in sorted(false_scores, key=lambda x: -x[1])[:3]:
            print(f"  - {o:<22} {s:.3f}")

    # =================================================================
    # Summary
    # =================================================================
    separable = sum(1 for g in all_gaps if g > 0)
    clean = sum(1 for g in all_gaps if g > 0.05)
    mean_gap = sum(all_gaps) / len(all_gaps)

    print(f"\n{'=' * 75}")
    print("SUMMARY")
    print(f"{'=' * 75}")
    print(f"Total behaviors:   {len(all_gaps)}")
    print(f"Separable (gap>0): {separable}/{len(all_gaps)}")
    print(f"Clean (gap>0.05):  {clean}/{len(all_gaps)}")
    print(f"Mean gap:          {mean_gap:+.3f}")
    print(f"Min gap:           {min(all_gaps):+.3f}")
    print(f"Max gap:           {max(all_gaps):+.3f}")

    if failures:
        print(f"\nFAILURES:")
        for f in failures:
            print(f"  - {f}")

    # =================================================================
    # Threshold sweep
    # =================================================================
    print(f"\n{'=' * 75}")
    print("THRESHOLD SWEEP (embedding only, before tag filter)")
    print(f"{'=' * 75}")

    for threshold in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        tp = fp = tn = fn = 0
        for bdata in behaviors.values():
            tv = target_vecs[bdata["target"]]
            for obj in bdata["true"]:
                s = _cos(tv, obj_vecs[obj])
                if s >= threshold:
                    tp += 1
                else:
                    fn += 1
            for obj in bdata["false"]:
                s = _cos(tv, obj_vecs[obj])
                if s >= threshold:
                    fp += 1
                else:
                    tn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )
        print(
            f"  t={threshold:.2f}  "
            f"TP={tp:>3} FP={fp:>3} FN={fn:>3} TN={tn:>3}  "
            f"P={precision:.2f} R={recall:.2f} F1={f1:.2f}"
        )

    # =================================================================
    # Key scenarios walkthrough
    # =================================================================
    print(f"\n{'=' * 75}")
    print("SCENARIO WALKTHROUGHS")
    print(f"{'=' * 75}")

    print("\n--- Medusa petrifies villager, wolf should stop ---")
    ws = _cos(target_vecs["small prey animals and creatures"], obj_vecs["Villager"])
    print(f"  Wolf target 'small prey animals' vs Villager identity: {ws:.3f}")
    print(f"  Wolf eat has required_tags=[LIVING]")
    print(f"  Before petrify: embedding match ({ws:.3f}) + LIVING present  -> TARGET")
    print(f"  After petrify:  embedding match ({ws:.3f}) + LIVING absent   -> DROPPED")
    print(f"  Embedding unchanged. Tag filter instant. No re-embed needed.")

    print("\n--- Firefighter + tree catches fire ---")
    ft = _cos(target_vecs["fires and burning things"], obj_vecs["Oak Tree"])
    fc = _cos(target_vecs["fires and burning things"], obj_vecs["Campfire"])
    print(f"  Firefighter target vs Oak Tree:  {ft:.3f}")
    print(f"  Firefighter target vs Campfire:  {fc:.3f}")
    print(f"  Firefighter has required_tags=[HEAT_SOURCE]")
    print(f"  Tree not on fire: HEAT_SOURCE absent -> filtered out (embedding irrelevant)")
    print(f"  Tree catches fire: HEAT_SOURCE added -> tag filter passes")
    print(f"  Embedding sim {ft:.3f} is moderate — threshold decides if it matches")
    print(f"  But campfire always matches: {fc:.3f} + HEAT_SOURCE present")

    print("\n--- Cop + Donut + Robber ---")
    cd = _cos(target_vecs["food, especially donuts"], obj_vecs["Donut"])
    cr = _cos(target_vecs["food, especially donuts"], obj_vecs["Robber"])
    dd = _cos(target_vecs["criminals and lawbreakers"], obj_vecs["Robber"])
    dv = _cos(target_vecs["criminals and lawbreakers"], obj_vecs["Villager"])
    print(f"  Cop eat target vs Donut:    {cd:.3f}  (should match)")
    print(f"  Cop eat target vs Robber:   {cr:.3f}  (should not match)")
    print(f"  Cop destroy target vs Robber:   {dd:.3f}  (should match)")
    print(f"  Cop destroy target vs Villager: {dv:.3f}  (should not match)")
    print(f"  Behavior priority: eat > destroy > flee")
    print(f"  Donut present -> cop eats. Donut gone -> cop attacks robber.")


asyncio.run(test())
