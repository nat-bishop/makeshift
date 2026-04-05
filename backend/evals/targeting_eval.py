"""Targeting pipeline evaluation — test the proposed identity + tag filter system.

Simulates the proposed two-stage targeting pipeline:
  Stage 1: Tag filter (boolean check on object tags)
  Stage 2: Embedding similarity (identity only, no tags in embedding)

Compares against the current single-embedding system to show where each
approach succeeds and fails.

Requires Ollama running with qwen3-embedding:0.6b pulled.

Usage:
    cd backend && uv run python -m evals.targeting_eval
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


# ---------------------------------------------------------------------------
# Proposed new identity string (no tags, includes substance)
# ---------------------------------------------------------------------------

SIZE_PHRASES: dict[str, str] = {
    "tiny": "tiny",
    "small": "small",
    "large": "large",
    "huge": "towering and huge",
}


def build_identity_string_v2(
    name: str,
    visual_description: str,
    size_category: str,
    substance: str,
) -> str:
    """Build a STABLE identity string — no tags, includes substance."""
    parts = [name, visual_description]
    if size_category in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size_category])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Two-stage matching
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 0.5     # pure embedding mode (no tag requirements)
LOOSE_THRESHOLD = 0.3     # tag-assisted mode (tags already confirmed state)


def passes_tag_filter(
    obj_tags: set[str],
    require_any: list[str],
    exclude: list[str],
) -> bool:
    """Stage 1: boolean tag filter."""
    for tag in exclude:
        if tag in obj_tags:
            return False
    if not require_any:
        return True
    return any(tag in obj_tags for tag in require_any)


def is_target_v2(
    embedding_sim: float,
    obj_tags: set[str],
    require_any: list[str],
    exclude: list[str],
) -> bool:
    """Two-stage pipeline: tag filter then embedding."""
    has_tag_requirements = bool(require_any) or bool(exclude)

    if has_tag_requirements:
        if not passes_tag_filter(obj_tags, require_any, exclude):
            return False
        # Tags matched — use loose embedding threshold
        return embedding_sim >= LOOSE_THRESHOLD
    else:
        # Pure embedding mode
        return embedding_sim >= MATCH_THRESHOLD


def is_target_v1(embedding_sim: float) -> bool:
    """Current system: single embedding threshold."""
    return embedding_sim >= MATCH_THRESHOLD


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------


@dataclass
class GameObject:
    """An object in the scene."""
    name: str
    visual: str
    size: str
    substance: str
    tags: set[str]


@dataclass
class Behavior:
    """A creature's behavior with targeting."""
    verb: str
    target_text: str
    require_any_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    """A targeting scenario to evaluate."""
    name: str
    description: str
    # The creature doing the targeting
    creature: GameObject
    behavior: Behavior
    # Objects in the scene
    objects: list[GameObject]
    # Which objects SHOULD be targeted (by name)
    expected_targets: set[str]


SCENARIOS: list[Scenario] = [
    # ===================================================================
    # FIREFIGHTER SCENARIOS — the core "flammable vs on fire" problem
    # ===================================================================
    Scenario(
        name="firefighter_burning_vs_flammable",
        description="Firefighter should only target things ON FIRE, not merely flammable",
        creature=GameObject("Firefighter", "muscular figure in yellow turnout gear", "medium",
                            "flesh", {"LIVING"}),
        behavior=Behavior("destroy", "fires and burning things",
                          require_any_tags=["HEAT_SOURCE"]),
        objects=[
            GameObject("Wooden Spoon", "a smooth wooden cooking spoon", "small",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Burning Spoon", "a smooth wooden cooking spoon", "small",
                       "wood", {"RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            GameObject("Campfire", "dancing orange flames on a pile of logs", "medium",
                       "fire", {"GAS", "HEAT_SOURCE", "HOT"}),
            GameObject("Wooden Table", "a sturdy oak dining table", "large",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Burning Table", "a sturdy oak dining table", "large",
                       "wood", {"RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            GameObject("Rock", "a rough gray boulder", "medium",
                       "stone", {"RIGID", "HEAVY"}),
        ],
        expected_targets={"Burning Spoon", "Campfire", "Burning Table"},
    ),

    # ===================================================================
    # WOLF / PREDATOR SCENARIOS — living vs petrified
    # ===================================================================
    Scenario(
        name="wolf_living_prey",
        description="Wolf targets living prey, ignores petrified/dead objects",
        creature=GameObject("Wolf", "gray wolf with sharp teeth", "medium",
                            "flesh", {"LIVING", "HOSTILE"}),
        behavior=Behavior("destroy", "small prey animals and living creatures",
                          require_any_tags=["LIVING"]),
        objects=[
            GameObject("Rabbit", "a small fluffy brown rabbit", "small",
                       "flesh", {"LIVING"}),
            GameObject("Stone Rabbit", "a small fluffy brown rabbit", "small",
                       "stone", {"RIGID", "BREAKABLE"}),
            GameObject("Villager", "a frightened peasant in brown clothes", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Petrified Villager", "a frightened peasant in brown clothes", "medium",
                       "stone", {"RIGID", "BREAKABLE", "BRITTLE"}),
            GameObject("Wooden Sword", "a roughly carved wooden practice sword", "small",
                       "wood", {"RIGID", "FLAMMABLE"}),
        ],
        expected_targets={"Rabbit", "Villager"},
    ),

    # ===================================================================
    # GUARD / PROTECT SCENARIOS — hostile vs friendly
    # ===================================================================
    Scenario(
        name="guard_protects_innocents",
        description="Guard destroys hostile creatures, ignores friendly ones",
        creature=GameObject("Guard", "armored knight with a sword", "medium",
                            "metal", {"LIVING"}),
        behavior=Behavior("destroy", "hostile enemies and monsters",
                          require_any_tags=["HOSTILE"]),
        objects=[
            GameObject("Goblin", "a sneaky green goblin with a dagger", "small",
                       "flesh", {"LIVING", "HOSTILE"}),
            GameObject("Dragon", "an enormous red dragon", "huge",
                       "flesh", {"LIVING", "HOSTILE", "FLYING", "HEAT_SOURCE"}),
            GameObject("Villager", "a friendly farmer in overalls", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Dog", "a friendly golden retriever", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Cursed Villager", "a friendly farmer in overalls", "medium",
                       "flesh", {"LIVING", "HOSTILE"}),
        ],
        expected_targets={"Goblin", "Dragon", "Cursed Villager"},
    ),

    # ===================================================================
    # HEALER SCENARIOS — living + not hostile
    # ===================================================================
    Scenario(
        name="healer_targets_wounded_allies",
        description="Healer protects living non-hostile creatures",
        creature=GameObject("Cleric", "a robed figure with a glowing staff", "medium",
                            "cloth", {"LIVING"}),
        behavior=Behavior("protect", "injured allies and innocent creatures",
                          require_any_tags=["LIVING"], exclude_tags=["HOSTILE"]),
        objects=[
            GameObject("Villager", "a frightened peasant", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Rabbit", "a wounded rabbit", "small",
                       "flesh", {"LIVING"}),
            GameObject("Goblin", "a sneaky goblin", "small",
                       "flesh", {"LIVING", "HOSTILE"}),
            GameObject("Stone Statue", "a marble statue of a warrior", "medium",
                       "stone", {"RIGID"}),
        ],
        expected_targets={"Villager", "Rabbit"},
    ),

    # ===================================================================
    # PURE IDENTITY — no state requirements (embedding-only)
    # ===================================================================
    Scenario(
        name="cop_eats_donuts",
        description="Cop targets food by identity only — no tag requirements",
        creature=GameObject("Officer Johnson", "stern police officer in blue uniform", "medium",
                            "flesh", {"LIVING"}),
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
    ),

    # ===================================================================
    # MAGNETIC CREATURE — targets metallic things
    # ===================================================================
    Scenario(
        name="magnet_attracts_metal",
        description="Magnetic creature follows metallic objects",
        creature=GameObject("Living Magnet", "a floating horseshoe magnet", "small",
                            "metal", {"LIVING", "MAGNETIC"}),
        behavior=Behavior("follow", "metal objects and metallic things",
                          require_any_tags=["METALLIC"]),
        objects=[
            GameObject("Iron Key", "a rusty old iron key", "tiny",
                       "metal", {"METALLIC", "RIGID"}),
            GameObject("Steel Sword", "a gleaming blade", "medium",
                       "metal", {"METALLIC", "RIGID", "SHARP"}),
            GameObject("Wooden Shield", "a round wooden shield", "medium",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Glass Bottle", "a clear glass potion bottle", "small",
                       "glass", {"BREAKABLE", "REFLECTIVE"}),
        ],
        expected_targets={"Iron Key", "Steel Sword"},
    ),

    # ===================================================================
    # FREEZE MAGE — targets wet things to freeze them
    # ===================================================================
    Scenario(
        name="freeze_mage_targets_wet",
        description="Ice mage targets wet objects to freeze them",
        creature=GameObject("Ice Mage", "a blue-robed wizard crackling with frost", "medium",
                            "cloth", {"LIVING", "COLD"}),
        behavior=Behavior("destroy", "wet and soaked things",
                          require_any_tags=["WET"]),
        objects=[
            GameObject("Wet Villager", "a drenched peasant", "medium",
                       "flesh", {"LIVING", "WET"}),
            GameObject("Dry Villager", "a peasant in dry clothes", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Puddle", "a shallow pool of water", "small",
                       "water", {"LIQUID", "WET"}),
            GameObject("Oil Slick", "a dark pool of slippery oil", "small",
                       "oil", {"LIQUID", "FLAMMABLE"}),
        ],
        expected_targets={"Wet Villager", "Puddle"},
    ),

    # ===================================================================
    # FLEE SCENARIOS — creature runs from fire
    # ===================================================================
    Scenario(
        name="animal_flees_fire",
        description="Deer flees from things on fire, not from flammable things",
        creature=GameObject("Deer", "a graceful brown deer", "medium",
                            "flesh", {"LIVING"}),
        behavior=Behavior("flee", "fire and burning things",
                          require_any_tags=["HEAT_SOURCE"]),
        objects=[
            GameObject("Campfire", "dancing orange flames", "medium",
                       "fire", {"GAS", "HEAT_SOURCE", "HOT"}),
            GameObject("Burning Tree", "a tall oak tree engulfed in flame", "large",
                       "wood", {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            GameObject("Normal Tree", "a tall green oak tree", "large",
                       "wood", {"FLAMMABLE"}),
            GameObject("Rock", "a gray boulder", "medium",
                       "stone", {"RIGID", "HEAVY"}),
            GameObject("Torch", "a wooden stick with a burning tip", "small",
                       "wood", {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
        ],
        expected_targets={"Campfire", "Burning Tree", "Torch"},
    ),

    # ===================================================================
    # SCAVENGER — targets non-living objects (inverse tag filter)
    # ===================================================================
    Scenario(
        name="scavenger_targets_objects",
        description="Scavenger investigates non-living objects, ignores creatures",
        creature=GameObject("Raccoon", "a curious raccoon with a striped tail", "small",
                            "flesh", {"LIVING"}),
        behavior=Behavior("investigate", "interesting objects and treasures",
                          exclude_tags=["LIVING"]),
        objects=[
            GameObject("Gold Coin", "a shiny gold coin", "tiny",
                       "metal", {"METALLIC", "REFLECTIVE"}),
            GameObject("Gem", "a sparkling red ruby", "tiny",
                       "glass", {"REFLECTIVE", "BREAKABLE"}),
            GameObject("Villager", "a peasant walking by", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Sleeping Dog", "a snoring brown dog", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Treasure Chest", "a wooden chest with gold trim", "medium",
                       "wood", {"RIGID"}),
        ],
        expected_targets={"Gold Coin", "Gem", "Treasure Chest"},
    ),

    # ===================================================================
    # ELECTRIC SCENARIOS — targets conductive things
    # ===================================================================
    Scenario(
        name="electric_eel_targets_wet",
        description="Electric eel attacks wet/conductive targets",
        creature=GameObject("Electric Eel", "a crackling blue eel", "medium",
                            "flesh", {"LIVING", "ELECTRIC", "WET"}),
        behavior=Behavior("destroy", "wet creatures and conductive things",
                          require_any_tags=["WET", "METALLIC"]),
        objects=[
            GameObject("Wet Knight", "an armored knight soaked in water", "medium",
                       "metal", {"LIVING", "METALLIC", "RIGID", "WET"}),
            GameObject("Dry Knight", "an armored knight in polished armor", "medium",
                       "metal", {"LIVING", "METALLIC", "RIGID"}),
            GameObject("Wet Peasant", "a drenched farmer", "medium",
                       "flesh", {"LIVING", "WET"}),
            GameObject("Dry Peasant", "a farmer in dry clothes", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Wooden Barrel", "an old oak barrel", "medium",
                       "wood", {"RIGID", "FLAMMABLE"}),
        ],
        expected_targets={"Wet Knight", "Dry Knight", "Wet Peasant"},
    ),

    # ===================================================================
    # TOXIC CLEANUP — hazmat worker targets toxic things
    # ===================================================================
    Scenario(
        name="hazmat_cleans_toxic",
        description="Hazmat worker targets toxic substances",
        creature=GameObject("Hazmat Worker", "figure in a yellow hazmat suit", "medium",
                            "cloth", {"LIVING"}),
        behavior=Behavior("destroy", "toxic waste and poisonous substances",
                          require_any_tags=["TOXIC"]),
        objects=[
            GameObject("Toxic Slime", "a bubbling green puddle of slime", "small",
                       "slime", {"LIQUID", "STICKY", "TOXIC"}),
            GameObject("Poison Mushroom", "a purple spotted mushroom", "tiny",
                       "flesh", {"LIVING", "TOXIC"}),
            GameObject("Clean Water", "a clear pool of water", "small",
                       "water", {"LIQUID", "WET"}),
            GameObject("Normal Mushroom", "a brown edible mushroom", "tiny",
                       "flesh", {"LIVING"}),
            GameObject("Acid Pool", "a hissing green pool", "small",
                       "slime", {"LIQUID", "ACIDIC", "TOXIC"}),
        ],
        expected_targets={"Toxic Slime", "Poison Mushroom", "Acid Pool"},
    ),

    # ===================================================================
    # CREATIVE / EDGE CASES
    # ===================================================================
    Scenario(
        name="cat_chases_flying_things",
        description="Cat investigates flying objects (butterflies, birds)",
        creature=GameObject("Cat", "a curious orange tabby cat", "small",
                            "flesh", {"LIVING"}),
        behavior=Behavior("investigate", "flying things and birds",
                          require_any_tags=["FLYING"]),
        objects=[
            GameObject("Butterfly", "a delicate blue butterfly", "tiny",
                       "flesh", {"LIVING", "FLYING"}),
            GameObject("Eagle", "a majestic bald eagle", "medium",
                       "flesh", {"LIVING", "FLYING", "HOSTILE"}),
            GameObject("Dead Bird", "a fallen sparrow", "tiny",
                       "flesh", set()),
            GameObject("Ball of Yarn", "a colorful ball of yarn", "small",
                       "cloth", {"BOUNCY"}),
            GameObject("Balloon", "a red helium balloon", "small",
                       "rubber", {"FLYING", "BOUNCY"}),
        ],
        expected_targets={"Butterfly", "Eagle", "Balloon"},
    ),

    Scenario(
        name="moth_attracted_to_light",
        description="Moth follows glowing/hot things",
        creature=GameObject("Giant Moth", "a large fuzzy brown moth", "medium",
                            "flesh", {"LIVING", "FLYING"}),
        behavior=Behavior("follow", "bright lights and glowing things",
                          require_any_tags=["GLOWING", "HEAT_SOURCE"]),
        objects=[
            GameObject("Lantern", "a warm glowing iron lantern", "small",
                       "metal", {"METALLIC", "HEAT_SOURCE", "GLOWING"}),
            GameObject("Campfire", "a crackling campfire", "medium",
                       "fire", {"GAS", "HEAT_SOURCE", "HOT"}),
            GameObject("Dark Rock", "a dull gray stone", "medium",
                       "stone", {"RIGID", "HEAVY"}),
            GameObject("Firefly", "a tiny blinking firefly", "tiny",
                       "flesh", {"LIVING", "FLYING", "GLOWING"}),
        ],
        expected_targets={"Lantern", "Campfire", "Firefly"},
    ),

    Scenario(
        name="dog_follows_owner_not_enemies",
        description="Loyal dog follows living non-hostile things (its 'family')",
        creature=GameObject("Dog", "a loyal golden retriever", "medium",
                            "flesh", {"LIVING"}),
        behavior=Behavior("follow", "people and friendly creatures",
                          require_any_tags=["LIVING"], exclude_tags=["HOSTILE"]),
        objects=[
            GameObject("Owner", "a kind-looking person", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Child", "a small laughing child", "small",
                       "flesh", {"LIVING"}),
            GameObject("Goblin", "a snarling green goblin", "small",
                       "flesh", {"LIVING", "HOSTILE"}),
            GameObject("Zombie", "a shambling undead creature", "medium",
                       "flesh", {"LIVING", "HOSTILE"}),
            GameObject("Bone", "a large white bone", "small",
                       "bone", {"RIGID"}),
        ],
        expected_targets={"Owner", "Child"},
    ),

    # ===================================================================
    # STATE TRANSITION — same object, before and after
    # ===================================================================
    Scenario(
        name="firefighter_state_transition",
        description="Same table before/after catching fire — tests state sensitivity",
        creature=GameObject("Firefighter", "muscular figure in yellow turnout gear", "medium",
                            "flesh", {"LIVING"}),
        behavior=Behavior("destroy", "fires and burning things",
                          require_any_tags=["HEAT_SOURCE"]),
        objects=[
            # Same table, two states
            GameObject("Table (normal)", "a sturdy oak dining table", "large",
                       "wood", {"RIGID", "FLAMMABLE"}),
            GameObject("Table (burning)", "a sturdy oak dining table", "large",
                       "wood", {"RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            # Same tree, two states
            GameObject("Tree (normal)", "a tall green oak tree", "large",
                       "wood", {"FLAMMABLE"}),
            GameObject("Tree (burning)", "a tall green oak tree", "large",
                       "wood", {"FLAMMABLE", "HEAT_SOURCE", "HOT"}),
            # Non-combustible
            GameObject("Stone Wall", "a thick gray stone wall", "huge",
                       "stone", {"RIGID", "HEAVY"}),
        ],
        expected_targets={"Table (burning)", "Tree (burning)"},
    ),

    Scenario(
        name="wolf_petrification_transition",
        description="Same villager before/after petrification — tests state sensitivity",
        creature=GameObject("Wolf", "gray wolf with sharp teeth", "medium",
                            "flesh", {"LIVING", "HOSTILE"}),
        behavior=Behavior("destroy", "prey animals and living creatures",
                          require_any_tags=["LIVING"]),
        objects=[
            GameObject("Villager (alive)", "a frightened peasant", "medium",
                       "flesh", {"LIVING"}),
            GameObject("Villager (petrified)", "a frightened peasant", "medium",
                       "stone", {"RIGID", "BREAKABLE", "BRITTLE"}),
            GameObject("Chicken (alive)", "a plump white chicken", "small",
                       "flesh", {"LIVING"}),
            GameObject("Chicken (frozen)", "a plump white chicken", "small",
                       "ice", {"FROZEN", "RIGID", "COLD", "BRITTLE"}),
        ],
        expected_targets={"Villager (alive)", "Chicken (alive)"},
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_scenario(
    scenario: Scenario,
    embeddings_cache: dict[str, list[float]],
) -> dict:
    """Run one scenario, return results."""
    # Get behavior target embedding
    behavior_emb = embeddings_cache[scenario.behavior.target_text]

    results = []
    v1_correct = 0
    v2_correct = 0

    for obj in scenario.objects:
        # V1: current system — tags IN embedding
        v1_key = f"v1:{obj.name}:{obj.visual}:{obj.size}:{sorted(obj.tags)}"
        v1_emb = embeddings_cache[v1_key]
        v1_sim = _cosine_sim(behavior_emb, v1_emb)
        v1_targeted = is_target_v1(v1_sim)

        # V2: proposed system — stable identity, no tags
        v2_key = f"v2:{obj.name}:{obj.visual}:{obj.size}:{obj.substance}"
        v2_emb = embeddings_cache[v2_key]
        v2_sim = _cosine_sim(behavior_emb, v2_emb)
        v2_targeted = is_target_v2(
            v2_sim, obj.tags,
            scenario.behavior.require_any_tags,
            scenario.behavior.exclude_tags,
        )

        should_target = obj.name in scenario.expected_targets

        v1_ok = v1_targeted == should_target
        v2_ok = v2_targeted == should_target
        if v1_ok:
            v1_correct += 1
        if v2_ok:
            v2_correct += 1

        results.append({
            "object": obj.name,
            "tags": sorted(obj.tags),
            "should_target": should_target,
            "v1_sim": round(v1_sim, 4),
            "v1_targeted": v1_targeted,
            "v1_correct": v1_ok,
            "v2_sim": round(v2_sim, 4),
            "v2_tag_pass": passes_tag_filter(
                obj.tags,
                scenario.behavior.require_any_tags,
                scenario.behavior.exclude_tags,
            ),
            "v2_targeted": v2_targeted,
            "v2_correct": v2_ok,
        })

    return {
        "name": scenario.name,
        "description": scenario.description,
        "behavior": f"{scenario.behavior.verb} -> \"{scenario.behavior.target_text}\"",
        "require_any_tags": scenario.behavior.require_any_tags,
        "exclude_tags": scenario.behavior.exclude_tags,
        "v1_accuracy": f"{v1_correct}/{len(scenario.objects)}",
        "v2_accuracy": f"{v2_correct}/{len(scenario.objects)}",
        "objects": results,
    }


async def main() -> None:
    # Check Ollama
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception:
        print("Error: Ollama not available at http://127.0.0.1:11434")  # noqa: T201
        sys.exit(1)

    # Collect all texts to embed
    texts_to_embed: dict[str, str] = {}  # key -> text

    for sc in SCENARIOS:
        # Behavior target
        texts_to_embed[sc.behavior.target_text] = sc.behavior.target_text

        for obj in sc.objects:
            # V1: current system (tags in embedding)
            tags = [Tag(t) for t in sorted(obj.tags) if t in Tag.__members__]
            v1_text = build_embed_string(obj.name, obj.visual, obj.size, tags)
            v1_key = f"v1:{obj.name}:{obj.visual}:{obj.size}:{sorted(obj.tags)}"
            texts_to_embed[v1_key] = v1_text

            # V2: proposed system (no tags, stable identity)
            v2_text = build_identity_string_v2(obj.name, obj.visual, obj.size, obj.substance)
            v2_key = f"v2:{obj.name}:{obj.visual}:{obj.size}:{obj.substance}"
            texts_to_embed[v2_key] = v2_text

    # Deduplicate texts for embedding
    unique_texts: list[str] = []
    text_to_idx: dict[str, int] = {}
    for text in texts_to_embed.values():
        if text not in text_to_idx:
            text_to_idx[text] = len(unique_texts)
            unique_texts.append(text)

    print(f"Embedding {len(unique_texts)} unique texts...")  # noqa: T201
    t0 = time.monotonic()
    all_embeddings = await embed_texts(unique_texts)
    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.2f}s\n")  # noqa: T201

    # Build cache: key -> embedding
    embeddings_cache: dict[str, list[float]] = {}
    for key, text in texts_to_embed.items():
        idx = text_to_idx[text]
        embeddings_cache[key] = all_embeddings[idx]

    # Run scenarios
    total_v1 = 0
    total_v2 = 0
    total_objects = 0
    all_results = []

    for sc in SCENARIOS:
        result = await run_scenario(sc, embeddings_cache)
        all_results.append(result)

        v1_n, v1_d = result["v1_accuracy"].split("/")
        v2_n, v2_d = result["v2_accuracy"].split("/")
        total_v1 += int(v1_n)
        total_v2 += int(v2_n)
        total_objects += int(v1_d)

    # Print results
    print("=" * 90)  # noqa: T201
    print("TARGETING PIPELINE EVALUATION")  # noqa: T201
    print(f"V1 = current (tags in embedding, single threshold {MATCH_THRESHOLD})")  # noqa: T201
    print(f"V2 = proposed (stable identity + tag filter, "  # noqa: T201
          f"loose threshold {LOOSE_THRESHOLD} when tags match)")
    print("=" * 90)  # noqa: T201

    for result in all_results:
        print(f"\n{'-' * 90}")  # noqa: T201
        print(f"  {result['name']}")  # noqa: T201
        print(f"  {result['description']}")  # noqa: T201
        print(f"  Behavior: {result['behavior']}")  # noqa: T201
        if result["require_any_tags"]:
            print(f"  Require any: {result['require_any_tags']}")  # noqa: T201
        if result["exclude_tags"]:
            print(f"  Exclude: {result['exclude_tags']}")  # noqa: T201
        print(f"  V1: {result['v1_accuracy']}  |  V2: {result['v2_accuracy']}")  # noqa: T201
        print()  # noqa: T201

        header = (f"  {'Object':<30} {'Should':>6} | {'V1 sim':>7} {'V1':>4} {'V1ok':>4} | "
                  f"{'V2 sim':>7} {'Tags':>4} {'V2':>4} {'V2ok':>4}")
        print(header)  # noqa: T201
        print(f"  {'-' * 86}")  # noqa: T201

        for obj in result["objects"]:
            should = "YES" if obj["should_target"] else "no"
            v1_t = "YES" if obj["v1_targeted"] else "no"
            v1_ok = " ok " if obj["v1_correct"] else "FAIL"
            v2_tag = "YES" if obj["v2_tag_pass"] else "no"
            v2_t = "YES" if obj["v2_targeted"] else "no"
            v2_ok = " ok " if obj["v2_correct"] else "FAIL"

            # Highlight failures
            v1_mark = "*" if not obj["v1_correct"] else " "
            v2_mark = "*" if not obj["v2_correct"] else " "

            print(f" {v1_mark}{v2_mark}{obj['object']:<29} {should:>6} | "  # noqa: T201
                  f"{obj['v1_sim']:>7.3f} {v1_t:>4} {v1_ok:>4} | "
                  f"{obj['v2_sim']:>7.3f} {v2_tag:>4} {v2_t:>4} {v2_ok:>4}")

    # Summary
    print(f"\n{'=' * 90}")  # noqa: T201
    print("SUMMARY")  # noqa: T201
    print(f"{'=' * 90}")  # noqa: T201
    print(f"  Total objects across all scenarios: {total_objects}")  # noqa: T201
    print(f"  V1 (current)  correct: {total_v1}/{total_objects} "  # noqa: T201
          f"({100*total_v1/total_objects:.1f}%)")
    print(f"  V2 (proposed) correct: {total_v2}/{total_objects} "  # noqa: T201
          f"({100*total_v2/total_objects:.1f}%)")
    print()  # noqa: T201

    # Show all V1 failures
    v1_failures = []
    v2_failures = []
    for result in all_results:
        for obj in result["objects"]:
            if not obj["v1_correct"]:
                v1_failures.append(f"  {result['name']}: {obj['object']} "
                                   f"(sim={obj['v1_sim']:.3f}, "
                                   f"targeted={obj['v1_targeted']}, "
                                   f"should={obj['should_target']})")
            if not obj["v2_correct"]:
                v2_failures.append(f"  {result['name']}: {obj['object']} "
                                   f"(sim={obj['v2_sim']:.3f}, "
                                   f"tag_pass={obj['v2_tag_pass']}, "
                                   f"targeted={obj['v2_targeted']}, "
                                   f"should={obj['should_target']})")

    if v1_failures:
        print(f"V1 failures ({len(v1_failures)}):")  # noqa: T201
        for f in v1_failures:
            print(f)  # noqa: T201

    if v2_failures:
        print(f"\nV2 failures ({len(v2_failures)}):")  # noqa: T201
        for f in v2_failures:
            print(f)  # noqa: T201
    else:
        print("V2 failures: NONE")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
