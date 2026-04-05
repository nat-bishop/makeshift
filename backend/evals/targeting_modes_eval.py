"""Test three targeting modes to see what embeddings actually contribute.

Mode A: Tags only (no embeddings at all)
Mode B: Embeddings only (current system, no tags)
Mode C: Tags OR embeddings (use tags when present, embeddings when not)

Requires Ollama running with qwen3-embedding:0.6b pulled.

Usage:
    cd backend && uv run python -m evals.targeting_modes_eval
"""

from __future__ import annotations

import asyncio
import math
import sys
import time
from dataclasses import dataclass, field

import httpx

from app.embeddings import embed_texts

SIZE_PHRASES: dict[str, str] = {
    "tiny": "tiny",
    "small": "small",
    "large": "large",
    "huge": "towering and huge",
}


def build_identity_string(name: str, visual: str, size: str, substance: str) -> str:
    parts = [name, visual]
    if size in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


MATCH_THRESHOLD = 0.5


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def passes_tag_filter(obj_tags: set[str], require_any: list[str], exclude: list[str]) -> bool:
    for tag in exclude:
        if tag in obj_tags:
            return False
    if not require_any:
        return True
    return any(tag in obj_tags for tag in require_any)


@dataclass
class GameObject:
    name: str
    visual: str
    size: str
    substance: str
    tags: set[str]


@dataclass
class Behavior:
    verb: str
    target_text: str
    require_any_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    description: str
    behavior: Behavior
    objects: list[GameObject]
    expected_targets: set[str]
    category: str  # "state_dependent", "pure_identity", "mixed"


SCENARIOS: list[Scenario] = [
    # ===== STATE-DEPENDENT: tags should handle these =====
    Scenario(
        name="firefighter_vs_fire",
        description="Target burning things, not flammable things",
        behavior=Behavior("destroy", "fires and burning things",
                          require_any_tags=["HEAT_SOURCE"]),
        objects=[
            GameObject("Wooden Spoon", "a smooth wooden cooking spoon", "small", "wood",
                       {"RIGID", "FLAMMABLE"}),
            GameObject("Burning Spoon", "a smooth wooden cooking spoon", "small", "wood",
                       {"RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            GameObject("Campfire", "dancing orange flames on logs", "medium", "fire",
                       {"GAS", "HEAT_SOURCE", "HOT"}),
            GameObject("Rock", "a rough gray boulder", "medium", "stone",
                       {"RIGID", "HEAVY"}),
        ],
        expected_targets={"Burning Spoon", "Campfire"},
        category="state_dependent",
    ),
    Scenario(
        name="wolf_vs_living",
        description="Target living things, not petrified",
        behavior=Behavior("destroy", "prey animals and living creatures",
                          require_any_tags=["LIVING"]),
        objects=[
            GameObject("Rabbit", "a small fluffy brown rabbit", "small", "flesh",
                       {"LIVING"}),
            GameObject("Stone Rabbit", "a small fluffy brown rabbit", "small", "stone",
                       {"RIGID", "BREAKABLE"}),
            GameObject("Villager", "a frightened peasant", "medium", "flesh",
                       {"LIVING"}),
            GameObject("Petrified Villager", "a frightened peasant", "medium", "stone",
                       {"RIGID", "BREAKABLE", "BRITTLE"}),
        ],
        expected_targets={"Rabbit", "Villager"},
        category="state_dependent",
    ),
    Scenario(
        name="guard_vs_hostile",
        description="Attack hostile things, not friendly",
        behavior=Behavior("destroy", "hostile enemies and monsters",
                          require_any_tags=["HOSTILE"]),
        objects=[
            GameObject("Goblin", "a sneaky green goblin", "small", "flesh",
                       {"LIVING", "HOSTILE"}),
            GameObject("Villager", "a friendly farmer", "medium", "flesh",
                       {"LIVING"}),
            GameObject("Cursed Farmer", "a friendly farmer", "medium", "flesh",
                       {"LIVING", "HOSTILE"}),
        ],
        expected_targets={"Goblin", "Cursed Farmer"},
        category="state_dependent",
    ),
    Scenario(
        name="deer_flees_fire",
        description="Flee from burning, not from flammable",
        behavior=Behavior("flee", "fire and burning things",
                          require_any_tags=["HEAT_SOURCE"]),
        objects=[
            GameObject("Campfire", "dancing orange flames", "medium", "fire",
                       {"GAS", "HEAT_SOURCE", "HOT"}),
            GameObject("Normal Tree", "a tall green oak tree", "large", "wood",
                       {"FLAMMABLE"}),
            GameObject("Burning Tree", "a tall green oak tree", "large", "wood",
                       {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
        ],
        expected_targets={"Campfire", "Burning Tree"},
        category="state_dependent",
    ),
    Scenario(
        name="healer_protects_allies",
        description="Protect living non-hostile",
        behavior=Behavior("protect", "injured allies", require_any_tags=["LIVING"],
                          exclude_tags=["HOSTILE"]),
        objects=[
            GameObject("Villager", "a frightened peasant", "medium", "flesh", {"LIVING"}),
            GameObject("Goblin", "a sneaky goblin", "small", "flesh", {"LIVING", "HOSTILE"}),
            GameObject("Statue", "a marble statue", "medium", "stone", {"RIGID"}),
        ],
        expected_targets={"Villager"},
        category="state_dependent",
    ),

    # ===== PURE IDENTITY: embeddings needed here =====
    Scenario(
        name="cop_eats_donuts",
        description="Cop finds food by identity - no tag for 'is food'",
        behavior=Behavior("eat", "food, especially donuts"),
        objects=[
            GameObject("Donut", "a glazed sugary donut with rainbow sprinkles", "small",
                       "rubber", {"BREAKABLE"}),
            GameObject("Pizza", "a hot cheesy pepperoni pizza slice", "small",
                       "cloth", {"BREAKABLE"}),
            GameObject("Steel Sword", "a gleaming sharp blade", "medium",
                       "metal", {"SHARP", "METALLIC", "RIGID"}),
            GameObject("Rock", "a rough gray boulder", "medium",
                       "stone", {"RIGID", "HEAVY"}),
        ],
        expected_targets={"Donut", "Pizza"},
        category="pure_identity",
    ),
    Scenario(
        name="mouse_finds_cheese",
        description="Mouse targets cheese/food by identity",
        behavior=Behavior("eat", "cheese and small snacks"),
        objects=[
            GameObject("Cheese Wheel", "a round yellow wheel of swiss cheese", "small",
                       "rubber", {"BREAKABLE"}),
            GameObject("Cracker", "a crispy golden cracker", "tiny",
                       "ceramic", {"BREAKABLE"}),
            GameObject("Iron Helmet", "a heavy iron war helmet", "small",
                       "metal", {"METALLIC", "RIGID"}),
            GameObject("Boulder", "a massive gray rock", "large",
                       "stone", {"RIGID", "HEAVY"}),
        ],
        expected_targets={"Cheese Wheel", "Cracker"},
        category="pure_identity",
    ),
    Scenario(
        name="dragon_hoards_treasure",
        description="Dragon follows shiny treasure by identity",
        behavior=Behavior("follow", "treasure, gold, and jewels"),
        objects=[
            GameObject("Gold Coin", "a shiny gold coin", "tiny",
                       "metal", {"METALLIC", "REFLECTIVE"}),
            GameObject("Ruby", "a sparkling red gem", "tiny",
                       "glass", {"REFLECTIVE", "BREAKABLE"}),
            GameObject("Wooden Barrel", "a plain oak barrel", "medium",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Villager", "a peasant farmer", "medium",
                       "flesh", {"LIVING"}),
        ],
        expected_targets={"Gold Coin", "Ruby"},
        category="pure_identity",
    ),
    Scenario(
        name="bookworm_investigates_books",
        description="Scholar investigates books and scrolls by identity",
        behavior=Behavior("investigate", "books, scrolls, and ancient texts"),
        objects=[
            GameObject("Ancient Tome", "a dusty leather-bound book with gold clasps", "small",
                       "cloth", {"FLAMMABLE"}),
            GameObject("Magic Scroll", "a rolled parchment with glowing runes", "tiny",
                       "cloth", {"FLAMMABLE"}),
            GameObject("Iron Shield", "a battered round iron shield", "medium",
                       "metal", {"METALLIC", "RIGID", "REFLECTIVE"}),
            GameObject("Fire Sword", "a gleaming blade wreathed in flame", "medium",
                       "metal", {"METALLIC", "RIGID", "SHARP", "HEAT_SOURCE"}),
        ],
        expected_targets={"Ancient Tome", "Magic Scroll"},
        category="pure_identity",
    ),
    Scenario(
        name="dog_fetches_balls",
        description="Dog follows balls and toys by identity",
        behavior=Behavior("follow", "balls and toys"),
        objects=[
            GameObject("Tennis Ball", "a fuzzy yellow-green tennis ball", "small",
                       "rubber", {"BOUNCY"}),
            GameObject("Red Ball", "a shiny red rubber ball", "small",
                       "rubber", {"BOUNCY"}),
            GameObject("Bone", "a large white dog bone", "small",
                       "bone", {"RIGID"}),
            GameObject("Rock", "a dull gray rock", "medium",
                       "stone", {"RIGID", "HEAVY"}),
            GameObject("Villager", "a person walking by", "medium",
                       "flesh", {"LIVING"}),
        ],
        expected_targets={"Tennis Ball", "Red Ball"},
        category="pure_identity",
    ),
    Scenario(
        name="pirate_seeks_ships",
        description="Pirate follows ships and boats by identity",
        behavior=Behavior("follow", "ships and boats"),
        objects=[
            GameObject("Wooden Ship", "a large sailing vessel with white sails", "huge",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Canoe", "a small wooden canoe", "medium",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Wooden Table", "a sturdy oak dining table", "large",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Anchor", "a heavy iron anchor", "medium",
                       "metal", {"METALLIC", "RIGID", "HEAVY"}),
        ],
        expected_targets={"Wooden Ship", "Canoe"},
        category="pure_identity",
    ),

    # ===== MIXED: could go either way =====
    Scenario(
        name="cat_chases_birds",
        description="Cat chases birds - FLYING tag OR identity?",
        behavior=Behavior("investigate", "birds and butterflies",
                          require_any_tags=["FLYING"]),
        objects=[
            GameObject("Eagle", "a majestic bald eagle", "medium", "flesh",
                       {"LIVING", "FLYING"}),
            GameObject("Butterfly", "a delicate blue butterfly", "tiny", "flesh",
                       {"LIVING", "FLYING"}),
            GameObject("Dead Bird", "a fallen sparrow", "tiny", "flesh", set()),
            GameObject("Balloon", "a red helium balloon", "small", "rubber",
                       {"FLYING", "BOUNCY"}),
        ],
        expected_targets={"Eagle", "Butterfly", "Balloon"},
        category="mixed",
    ),
    Scenario(
        name="magpie_collects_shiny",
        description="Magpie collects shiny things - REFLECTIVE tag works",
        behavior=Behavior("follow", "shiny objects",
                          require_any_tags=["REFLECTIVE"]),
        objects=[
            GameObject("Gold Coin", "a shiny gold coin", "tiny", "metal",
                       {"METALLIC", "REFLECTIVE"}),
            GameObject("Mirror", "a silver hand mirror", "small", "glass",
                       {"REFLECTIVE", "BREAKABLE"}),
            GameObject("Dull Rock", "a rough gray stone", "medium", "stone",
                       {"RIGID", "HEAVY"}),
            GameObject("Wooden Spoon", "a plain wooden spoon", "small", "wood",
                       {"RIGID"}),
        ],
        expected_targets={"Gold Coin", "Mirror"},
        category="mixed",
    ),
]


async def main() -> None:
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception:
        print("Error: Ollama not available")  # noqa: T201
        sys.exit(1)

    # Collect texts
    texts_to_embed: dict[str, str] = {}
    for sc in SCENARIOS:
        texts_to_embed[f"target:{sc.behavior.target_text}"] = sc.behavior.target_text
        for obj in sc.objects:
            key = f"id:{obj.name}:{obj.visual}:{obj.size}:{obj.substance}"
            texts_to_embed[key] = build_identity_string(
                obj.name, obj.visual, obj.size, obj.substance
            )

    unique_texts: list[str] = []
    text_to_idx: dict[str, int] = {}
    for text in texts_to_embed.values():
        if text not in text_to_idx:
            text_to_idx[text] = len(unique_texts)
            unique_texts.append(text)

    print(f"Embedding {len(unique_texts)} unique texts...")  # noqa: T201
    t0 = time.monotonic()
    all_embeddings = await embed_texts(unique_texts)
    print(f"Done in {time.monotonic() - t0:.2f}s\n")  # noqa: T201

    cache: dict[str, list[float]] = {}
    for key, text in texts_to_embed.items():
        cache[key] = all_embeddings[text_to_idx[text]]

    # Results by mode and category
    mode_scores: dict[str, dict[str, list[bool]]] = {
        "A (tags only)": {},
        "B (embeddings only)": {},
        "C (tags OR embed)": {},
    }

    print("=" * 100)  # noqa: T201
    print("TARGETING MODE COMPARISON")  # noqa: T201
    print("  Mode A: Tags only (embedding ignored entirely)")  # noqa: T201
    print("  Mode B: Embeddings only (tags ignored, threshold 0.5)")  # noqa: T201
    print("  Mode C: Tags when present, embeddings when not (the proposed design)")  # noqa: T201
    print("=" * 100)  # noqa: T201

    for sc in SCENARIOS:
        behavior_emb = cache[f"target:{sc.behavior.target_text}"]
        has_tags = bool(sc.behavior.require_any_tags) or bool(sc.behavior.exclude_tags)

        print(f"\n--- {sc.name} [{sc.category}] ---")  # noqa: T201
        print(f"    {sc.behavior.verb} -> \"{sc.behavior.target_text}\"")  # noqa: T201
        if sc.behavior.require_any_tags:
            print(f"    require: {sc.behavior.require_any_tags}")  # noqa: T201
        if sc.behavior.exclude_tags:
            print(f"    exclude: {sc.behavior.exclude_tags}")  # noqa: T201

        header = f"    {'Object':<25} {'Should':>6} | {'A:tag':>5} {'A':>4} | {'B:sim':>6} {'B':>4} | {'C':>4}"
        print(header)  # noqa: T201

        for obj in sc.objects:
            obj_key = f"id:{obj.name}:{obj.visual}:{obj.size}:{obj.substance}"
            obj_emb = cache[obj_key]
            sim = _cosine_sim(behavior_emb, obj_emb)
            should = obj.name in sc.expected_targets
            tag_pass = passes_tag_filter(
                obj.tags, sc.behavior.require_any_tags, sc.behavior.exclude_tags
            )
            emb_pass = sim >= MATCH_THRESHOLD

            # Mode A: tags only
            if has_tags:
                mode_a = tag_pass
            else:
                mode_a = True  # no filter = target everything (broken for pure identity)

            # Mode B: embeddings only
            mode_b = emb_pass

            # Mode C: tags when present, embeddings when not
            if has_tags:
                mode_c = tag_pass
            else:
                mode_c = emb_pass

            a_ok = mode_a == should
            b_ok = mode_b == should
            c_ok = mode_c == should

            for mode_name, correct in [("A (tags only)", a_ok),
                                        ("B (embeddings only)", b_ok),
                                        ("C (tags OR embed)", c_ok)]:
                mode_scores[mode_name].setdefault(sc.category, []).append(correct)

            a_mark = " ok " if a_ok else "FAIL"
            b_mark = " ok " if b_ok else "FAIL"
            c_mark = " ok " if c_ok else "FAIL"
            a_str = "YES" if mode_a else " no"
            b_str = "YES" if mode_b else " no"
            c_str = "YES" if mode_c else " no"

            print(f"    {obj.name:<25} {'YES' if should else ' no':>6} | "  # noqa: T201
                  f"{a_str:>5} {a_mark:>4} | {sim:>6.3f} {b_mark:>4} | {c_mark:>4}")

    # Summary
    print(f"\n{'=' * 100}")  # noqa: T201
    print("SUMMARY BY MODE AND CATEGORY")  # noqa: T201
    print(f"{'=' * 100}")  # noqa: T201

    categories = ["state_dependent", "pure_identity", "mixed"]
    for mode_name, cat_results in mode_scores.items():
        total_correct = 0
        total = 0
        print(f"\n  {mode_name}:")  # noqa: T201
        for cat in categories:
            results = cat_results.get(cat, [])
            if not results:
                continue
            correct = sum(results)
            total_correct += correct
            total += len(results)
            pct = 100 * correct / len(results) if results else 0
            print(f"    {cat:<20} {correct}/{len(results)} ({pct:.0f}%)")  # noqa: T201
        if total:
            print(f"    {'TOTAL':<20} {total_correct}/{total} "  # noqa: T201
                  f"({100*total_correct/total:.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
