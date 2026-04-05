"""Direct comparison: current system (main) vs proposed system.

Runs the same scenarios through both systems and shows exactly where
each one gets it right and wrong.

Current system: tags IN embedding, single dot-product threshold 0.5, raw query
Proposed system: tags for state (boolean), instructed embeddings for identity

Usage:
    cd backend && uv run python -m evals.system_comparison
"""

from __future__ import annotations

import asyncio
import math
import sys
import time
from dataclasses import dataclass, field

import httpx

from app.embeddings import build_embed_string, embed_texts
from app.models.tags import Tag

OLLAMA_URL = "http://127.0.0.1:11434"
THRESHOLD = 0.5
RETRIEVAL_PREFIX = "Instruct: Retrieve objects matching this description.\nQuery: "

SIZE_PHRASES = {"tiny": "tiny", "small": "small", "large": "large", "huge": "towering and huge"}


def build_identity_v2(name: str, visual: str, size: str, substance: str) -> str:
    parts = [name, visual]
    if size in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def tag_filter(obj_tags: set[str], require_any: list[str], exclude: list[str]) -> bool:
    for t in exclude:
        if t in obj_tags:
            return False
    if not require_any:
        return True
    return any(t in obj_tags for t in require_any)


@dataclass
class Obj:
    name: str
    visual: str
    size: str
    substance: str
    tags: set[str]


@dataclass
class Behavior:
    verb: str
    target: str
    target_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    description: str
    behavior: Behavior
    objects: list[Obj]
    expected: set[str]  # names of objects that SHOULD be targeted
    category: str  # "state", "identity", "mixed"


SCENARIOS = [
    # === STATE-DEPENDENT (the broken cases on main) ===
    Scenario("firefighter", "Should only target things currently ON FIRE",
             Behavior("destroy", "fires and burning things", ["HEAT_SOURCE"]),
             [Obj("Wooden Spoon", "a smooth cooking spoon", "small", "wood",
                  {"RIGID", "FLAMMABLE"}),
              Obj("Burning Spoon", "a smooth cooking spoon", "small", "wood",
                  {"RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"}),
              Obj("Campfire", "dancing orange flames", "medium", "fire",
                  {"GAS", "HEAT_SOURCE", "HOT"}),
              Obj("Normal Tree", "a tall green oak tree", "large", "wood",
                  {"FLAMMABLE"}),
              Obj("Burning Tree", "a tall green oak tree", "large", "wood",
                  {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
              Obj("Rock", "a rough gray boulder", "medium", "stone",
                  {"RIGID", "HEAVY"})],
             {"Burning Spoon", "Campfire", "Burning Tree"}, "state"),

    Scenario("wolf_petrify", "Should stop targeting petrified villager",
             Behavior("destroy", "prey animals and living creatures", ["LIVING"]),
             [Obj("Rabbit", "a small fluffy brown rabbit", "small", "flesh", {"LIVING"}),
              Obj("Villager", "a frightened peasant", "medium", "flesh", {"LIVING"}),
              Obj("Stone Rabbit", "a small fluffy brown rabbit", "small", "stone",
                  {"RIGID", "BREAKABLE"}),
              Obj("Petrified Villager", "a frightened peasant", "medium", "stone",
                  {"RIGID", "BREAKABLE", "BRITTLE"}),
              Obj("Wooden Sword", "a roughly carved sword", "small", "wood",
                  {"RIGID", "FLAMMABLE"})],
             {"Rabbit", "Villager"}, "state"),

    Scenario("guard_hostile", "Should only attack hostile things",
             Behavior("destroy", "hostile enemies", ["HOSTILE"]),
             [Obj("Goblin", "a sneaky green goblin", "small", "flesh",
                  {"LIVING", "HOSTILE"}),
              Obj("Villager", "a friendly farmer", "medium", "flesh", {"LIVING"}),
              Obj("Cursed Farmer", "a friendly farmer", "medium", "flesh",
                  {"LIVING", "HOSTILE"}),
              Obj("Dog", "a golden retriever", "medium", "flesh", {"LIVING"})],
             {"Goblin", "Cursed Farmer"}, "state"),

    Scenario("healer_no_enemies", "Should protect living non-hostile",
             Behavior("protect", "injured allies", ["LIVING"], ["HOSTILE"]),
             [Obj("Villager", "a peasant", "medium", "flesh", {"LIVING"}),
              Obj("Goblin", "a goblin", "small", "flesh", {"LIVING", "HOSTILE"}),
              Obj("Statue", "a marble statue", "medium", "stone", {"RIGID"})],
             {"Villager"}, "state"),

    Scenario("deer_flees_fire", "Should flee actual fire, not flammable things",
             Behavior("flee", "fire", ["HEAT_SOURCE"]),
             [Obj("Campfire", "dancing flames", "medium", "fire",
                  {"GAS", "HEAT_SOURCE"}),
              Obj("Torch", "a burning stick", "small", "wood",
                  {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
              Obj("Wooden Barrel", "an oak barrel", "medium", "wood",
                  {"RIGID", "FLAMMABLE"}),
              Obj("Rock", "a gray stone", "medium", "stone", {"RIGID", "HEAVY"})],
             {"Campfire", "Torch"}, "state"),

    Scenario("magnet_metal", "Should follow metallic objects only",
             Behavior("follow", "metal objects", ["METALLIC"]),
             [Obj("Iron Key", "a rusty key", "tiny", "metal", {"METALLIC", "RIGID"}),
              Obj("Steel Sword", "a blade", "medium", "metal",
                  {"METALLIC", "RIGID", "SHARP"}),
              Obj("Wooden Shield", "a wooden shield", "medium", "wood",
                  {"RIGID", "FLAMMABLE"}),
              Obj("Glass Bottle", "a potion bottle", "small", "glass",
                  {"BREAKABLE", "REFLECTIVE"})],
             {"Iron Key", "Steel Sword"}, "state"),

    Scenario("freeze_wet", "Should target wet things to freeze",
             Behavior("destroy", "wet things", ["WET"]),
             [Obj("Wet Villager", "a drenched peasant", "medium", "flesh",
                  {"LIVING", "WET"}),
              Obj("Dry Villager", "a peasant", "medium", "flesh", {"LIVING"}),
              Obj("Puddle", "a shallow pool", "small", "water", {"LIQUID", "WET"}),
              Obj("Oil Slick", "dark oil", "small", "oil", {"LIQUID", "FLAMMABLE"})],
             {"Wet Villager", "Puddle"}, "state"),

    Scenario("rust_monster", "Should eat metallic things",
             Behavior("eat", "metal", ["METALLIC"]),
             [Obj("Iron Sword", "a gleaming blade", "medium", "metal",
                  {"METALLIC", "RIGID", "SHARP"}),
              Obj("Gold Coin", "a shiny coin", "tiny", "metal",
                  {"METALLIC", "REFLECTIVE"}),
              Obj("Wooden Club", "a rough wooden club", "medium", "wood",
                  {"RIGID", "FLAMMABLE"}),
              Obj("Bone", "a white bone", "small", "bone", {"RIGID"})],
             {"Iron Sword", "Gold Coin"}, "state"),

    # === IDENTITY-ONLY (embeddings matter here) ===
    Scenario("cop_donuts", "Should find food by identity",
             Behavior("eat", "food, especially donuts"),
             [Obj("Donut", "a glazed donut with rainbow sprinkles", "small", "rubber",
                  {"BREAKABLE"}),
              Obj("Pizza", "a cheesy pepperoni pizza", "small", "cloth", {"BREAKABLE"}),
              Obj("Steel Sword", "a sharp blade", "medium", "metal",
                  {"SHARP", "METALLIC", "RIGID"}),
              Obj("Rock", "a gray boulder", "medium", "stone", {"RIGID", "HEAVY"})],
             {"Donut", "Pizza"}, "identity"),

    Scenario("dragon_treasure", "Should follow treasure by identity",
             Behavior("follow", "treasure, gold, and jewels"),
             [Obj("Gold Coin", "a shiny gold coin", "tiny", "metal",
                  {"METALLIC", "REFLECTIVE"}),
              Obj("Ruby", "a sparkling red gem", "tiny", "glass",
                  {"REFLECTIVE", "BREAKABLE"}),
              Obj("Crown", "a golden crown with diamonds", "small", "metal",
                  {"METALLIC", "REFLECTIVE"}),
              Obj("Wooden Barrel", "a plain oak barrel", "medium", "wood",
                  {"RIGID", "FLAMMABLE"}),
              Obj("Iron Sword", "a plain iron sword", "medium", "metal",
                  {"METALLIC", "RIGID", "SHARP"})],
             {"Gold Coin", "Ruby", "Crown"}, "identity"),

    Scenario("bookworm", "Should investigate books by identity",
             Behavior("investigate", "books, scrolls, and texts"),
             [Obj("Ancient Tome", "a dusty leather-bound book", "small", "cloth",
                  {"FLAMMABLE"}),
              Obj("Magic Scroll", "a rolled parchment with runes", "tiny", "cloth",
                  {"FLAMMABLE"}),
              Obj("Iron Shield", "a battered iron shield", "medium", "metal",
                  {"METALLIC", "RIGID"}),
              Obj("Fire Sword", "a blade wreathed in flame", "medium", "metal",
                  {"METALLIC", "RIGID", "SHARP", "HEAT_SOURCE"})],
             {"Ancient Tome", "Magic Scroll"}, "identity"),

    Scenario("dog_balls", "Should follow balls by identity",
             Behavior("follow", "tennis balls and toys"),
             [Obj("Tennis Ball", "a fuzzy yellow tennis ball", "small", "rubber",
                  {"BOUNCY"}),
              Obj("Red Ball", "a shiny red rubber ball", "small", "rubber", {"BOUNCY"}),
              Obj("Bone", "a white dog bone", "small", "bone", {"RIGID"}),
              Obj("Rock", "a gray rock", "medium", "stone", {"RIGID", "HEAVY"})],
             {"Tennis Ball", "Red Ball"}, "identity"),

    Scenario("cat_fish", "Should find fish by identity",
             Behavior("eat", "fish and seafood"),
             [Obj("Salmon", "a fresh pink salmon", "small", "flesh", {"LIVING"}),
              Obj("Goldfish", "a small orange goldfish", "tiny", "flesh", {"LIVING"}),
              Obj("Dog", "a friendly labrador", "medium", "flesh", {"LIVING"}),
              Obj("Rope", "a hemp rope", "small", "cloth", set())],
             {"Salmon", "Goldfish"}, "identity"),
]


async def main() -> None:
    try:
        httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).raise_for_status()
    except Exception:
        print("Ollama not available")  # noqa: T201
        sys.exit(1)

    # Collect all texts
    v1_texts: dict[str, str] = {}  # key -> text for current system
    v2_id_texts: dict[str, str] = {}  # key -> identity text (no tags)
    v2_query_texts: dict[str, str] = {}  # target -> instructed query

    for sc in SCENARIOS:
        # V1: raw target query
        v1_texts[f"q:{sc.behavior.target}"] = sc.behavior.target
        # V2: instructed target query
        v2_query_texts[f"iq:{sc.behavior.target}"] = f"{RETRIEVAL_PREFIX}{sc.behavior.target}"

        for obj in sc.objects:
            # V1: tags in embedding
            tag_enums = [Tag(t) for t in sorted(obj.tags) if t in Tag.__members__]
            v1_text = build_embed_string(obj.name, obj.visual, obj.size, tag_enums)
            v1_texts[f"v1:{sc.name}:{obj.name}"] = v1_text
            # V2: stable identity (no tags)
            v2_id_texts[f"v2:{obj.name}:{obj.substance}"] = build_identity_v2(
                obj.name, obj.visual, obj.size, obj.substance)

    # Embed everything
    all_texts = {}
    all_texts.update(v1_texts)
    all_texts.update(v2_id_texts)
    all_texts.update(v2_query_texts)

    unique: list[str] = []
    idx: dict[str, int] = {}
    for text in all_texts.values():
        if text not in idx:
            idx[text] = len(unique)
            unique.append(text)

    print(f"Embedding {len(unique)} texts...")  # noqa: T201
    t0 = time.monotonic()
    embs = await embed_texts(unique)
    print(f"Done in {time.monotonic()-t0:.1f}s\n")  # noqa: T201

    cache: dict[str, list[float]] = {}
    for key, text in all_texts.items():
        cache[key] = embs[idx[text]]

    # Score
    totals = {"state": [0, 0, 0, 0], "identity": [0, 0, 0, 0]}  # [v1_correct, v1_total, v2_correct, v2_total]

    print("=" * 95)  # noqa: T201
    print("CURRENT (main) vs PROPOSED — side by side")  # noqa: T201
    print("  Current: tags in embedding, raw query, threshold 0.5")  # noqa: T201
    print("  Proposed: tags for state (boolean) OR instructed embedding for identity")  # noqa: T201
    print("=" * 95)  # noqa: T201

    for sc in SCENARIOS:
        v1_q = cache[f"q:{sc.behavior.target}"]
        v2_q = cache[f"iq:{sc.behavior.target}"]
        has_tags = bool(sc.behavior.target_tags) or bool(sc.behavior.exclude_tags)

        v1_ok_count = 0
        v2_ok_count = 0

        print(f"\n--- {sc.name} [{sc.category}] ---")  # noqa: T201
        print(f"    {sc.description}")  # noqa: T201
        print(f"    {sc.behavior.verb} -> \"{sc.behavior.target}\"", end="")  # noqa: T201
        if sc.behavior.target_tags:
            print(f" target_tags: {sc.behavior.target_tags}", end="")  # noqa: T201
        if sc.behavior.exclude_tags:
            print(f" exclude: {sc.behavior.exclude_tags}", end="")  # noqa: T201
        print()  # noqa: T201

        hdr = (f"    {'Object':<22} {'Want':>4} | {'V1 sim':>6} {'V1':>5} "
               f"| {'V2':>5} {'How':>8}")
        print(hdr)  # noqa: T201
        print(f"    {'-' * 62}")  # noqa: T201

        for obj in sc.objects:
            should = obj.name in sc.expected

            # V1: current system
            v1_emb = cache[f"v1:{sc.name}:{obj.name}"]
            v1_sim = cosine(v1_q, v1_emb)
            v1_match = v1_sim >= THRESHOLD
            v1_ok = v1_match == should
            if v1_ok:
                v1_ok_count += 1

            # V2: proposed system
            if has_tags:
                v2_match = tag_filter(obj.tags, sc.behavior.target_tags,
                                      sc.behavior.exclude_tags)
                v2_how = "tag"
            else:
                v2_id_emb = cache[f"v2:{obj.name}:{obj.substance}"]
                v2_sim_val = cosine(v2_q, v2_id_emb)
                v2_match = v2_sim_val >= THRESHOLD
                v2_how = f"emb {v2_sim_val:.2f}"

            v2_ok = v2_match == should
            if v2_ok:
                v2_ok_count += 1

            want = "YES" if should else "no"
            v1_str = "YES" if v1_match else "no"
            v2_str = "YES" if v2_match else "no"
            v1_mark = " " if v1_ok else "*"
            v2_mark = " " if v2_ok else "*"

            print(f"  {v1_mark}{v2_mark} {obj.name:<21} {want:>4} | "  # noqa: T201
                  f"{v1_sim:>6.3f} {v1_str:>5} | {v2_str:>5} {v2_how:>8}")

        cat = sc.category
        totals[cat][0] += v1_ok_count
        totals[cat][1] += len(sc.objects)
        totals[cat][2] += v2_ok_count
        totals[cat][3] += len(sc.objects)

        print(f"    Score: V1 {v1_ok_count}/{len(sc.objects)}  |  "  # noqa: T201
              f"V2 {v2_ok_count}/{len(sc.objects)}")

    # Summary
    print(f"\n{'=' * 95}")  # noqa: T201
    print("SUMMARY")  # noqa: T201
    print(f"{'=' * 95}\n")  # noqa: T201

    grand_v1 = 0
    grand_v2 = 0
    grand_total = 0
    for cat in ["state", "identity"]:
        v1c, v1t, v2c, v2t = totals[cat]
        v1p = 100 * v1c / v1t if v1t else 0
        v2p = 100 * v2c / v2t if v2t else 0
        diff = v2p - v1p
        arrow = "+" if diff > 0 else ""
        print(f"  {cat:<12}  Current: {v1c}/{v1t} ({v1p:.0f}%)  "  # noqa: T201
              f"Proposed: {v2c}/{v2t} ({v2p:.0f}%)  [{arrow}{diff:.0f}%]")
        grand_v1 += v1c
        grand_v2 += v2c
        grand_total += v1t

    v1p = 100 * grand_v1 / grand_total
    v2p = 100 * grand_v2 / grand_total
    diff = v2p - v1p
    arrow = "+" if diff > 0 else ""
    print(f"\n  {'TOTAL':<12}  Current: {grand_v1}/{grand_total} ({v1p:.0f}%)  "  # noqa: T201
          f"Proposed: {grand_v2}/{grand_total} ({v2p:.0f}%)  [{arrow}{diff:.0f}%]")

    # List all failures
    print(f"\n  Current system failures:")  # noqa: T201
    print(f"  Proposed system failures:")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
