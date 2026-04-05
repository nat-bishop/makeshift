"""End-to-end targeting system validation.

Simulates Godot's VerbBehaviorSystem dual-mode targeting in Python with real
Ollama embeddings. Tests whether tag-filter + embedding targeting works across
multi-object scenes.

Requires Ollama running with qwen3-embedding:0.6b pulled.

Usage:
    cd backend && uv run python -m evals.targeting_test
    cd backend && uv run python -m evals.targeting_test --no-save
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.embeddings import build_identity_string, build_target_query, embed_texts

RESULTS_DIR = Path(__file__).parent / "results"
MATCH_THRESHOLD = 0.5  # Mirrors VerbBehaviorSystem.MATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ObjectBehavior:
    verb: str
    target: str
    target_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    expected_matches: set[str] = field(default_factory=set)
    expected_non_matches: set[str] = field(default_factory=set)


@dataclass
class SceneObject:
    name: str
    visual_description: str
    substance: str
    size_category: str = "medium"
    tags: list[str] = field(default_factory=list)
    behaviors: list[ObjectBehavior] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    description: str
    objects: list[SceneObject]
    critical: bool = True


# ---------------------------------------------------------------------------
# Matching logic — exact mirror of verb_behavior_system.gd:100-134
# ---------------------------------------------------------------------------


def passes_tag_filter(
    obj_tags: list[str], require_any: list[str], exclude: list[str],
) -> bool:
    for tag in exclude:
        if tag in obj_tags:
            return False
    if not require_any:
        return True
    return any(tag in obj_tags for tag in require_any)


def dot_product(a: list[float], b: list[float]) -> float:
    size = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(size))


def check_match(
    obj_tags: list[str],
    require_any_tags: list[str],
    exclude_tags: list[str],
    behavior_embedding: list[float],
    target_identity_embedding: list[float],
) -> tuple[bool, str, float]:
    """Returns (is_match, mode, similarity_score)."""
    has_tag_reqs = bool(require_any_tags) or bool(exclude_tags)
    if has_tag_reqs:
        passed = passes_tag_filter(obj_tags, require_any_tags, exclude_tags)
        return (passed, "tag", 0.0)
    else:
        if not behavior_embedding or not target_identity_embedding:
            return (False, "embedding", 0.0)
        sim = dot_product(behavior_embedding, target_identity_embedding)
        return (sim >= MATCH_THRESHOLD, "embedding", sim)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: list[Scenario] = [
    # 1. Tag mode: LIVING vs non-LIVING, HEAT_SOURCE vs FLAMMABLE
    Scenario(
        name="Forest Encounter",
        description="Tag-filter targeting: state tags separate living from petrified, heat from flammable",
        critical=True,
        objects=[
            SceneObject(
                name="Wolf",
                visual_description="a snarling gray wolf with sharp teeth",
                substance="flesh", tags=["LIVING", "HOSTILE"],
                behaviors=[
                    ObjectBehavior(
                        verb="destroy", target="small prey animals",
                        target_tags=["LIVING"],
                        expected_matches={"Rabbit"},
                        expected_non_matches={"Stone Rabbit", "Campfire", "Oak Tree"},
                    ),
                    ObjectBehavior(
                        verb="flee", target="fire and burning things",
                        target_tags=["HEAT_SOURCE"],
                        expected_matches={"Campfire"},
                        expected_non_matches={"Rabbit", "Stone Rabbit", "Oak Tree"},
                    ),
                ],
            ),
            SceneObject(
                name="Rabbit",
                visual_description="a small brown rabbit with long ears",
                substance="flesh", size_category="small", tags=["LIVING"],
            ),
            SceneObject(
                name="Stone Rabbit",
                visual_description="a small brown rabbit with long ears, turned to stone",
                substance="stone", size_category="small", tags=["RIGID", "BREAKABLE"],
            ),
            SceneObject(
                name="Campfire",
                visual_description="a crackling campfire with orange flames",
                substance="fire", tags=["HEAT_SOURCE", "HOT"],
            ),
            SceneObject(
                name="Oak Tree",
                visual_description="a tall oak tree with green leaves",
                substance="wood", size_category="large", tags=["FLAMMABLE"],
            ),
        ],
    ),

    # 2. Cross-mode: embedding for food, tags for criminals
    Scenario(
        name="Town Square",
        description="Cross-mode targeting: cop uses embedding to find food, tags to find criminals",
        critical=True,
        objects=[
            SceneObject(
                name="Officer Johnson",
                visual_description="a stern police officer in blue uniform",
                substance="flesh", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="eat", target="food, especially donuts",
                        expected_matches={"Donut", "Pizza"},
                        expected_non_matches={"Rock", "Robber", "Steel Sword"},
                    ),
                    ObjectBehavior(
                        verb="destroy", target="criminals and lawbreakers",
                        target_tags=["HOSTILE"],
                        expected_matches={"Robber"},
                        expected_non_matches={"Donut", "Pizza", "Rock", "Steel Sword"},
                    ),
                ],
            ),
            SceneObject(
                name="Donut",
                visual_description="a glazed sugary donut with rainbow sprinkles",
                substance="rubber", size_category="small", tags=["BREAKABLE"],
            ),
            SceneObject(
                name="Pizza",
                visual_description="a hot cheesy pizza slice with pepperoni",
                substance="cloth", size_category="small", tags=["BREAKABLE"],
            ),
            SceneObject(
                name="Rock",
                visual_description="a rough gray boulder",
                substance="stone", tags=["RIGID", "HEAVY"],
            ),
            SceneObject(
                name="Robber",
                visual_description="a masked criminal in dark clothes carrying a bag of loot",
                substance="flesh", tags=["LIVING", "HOSTILE"],
            ),
            SceneObject(
                name="Steel Sword",
                visual_description="a long gleaming steel blade with a leather grip",
                substance="metal", tags=["SHARP"],
            ),
        ],
    ),

    # 3. Embedding discrimination: treasure vs non-treasure
    Scenario(
        name="Dragon's Lair",
        description="Embedding-mode targeting: dragon follows treasure, no false positives for water/ice",
        critical=True,
        objects=[
            SceneObject(
                name="Dragon",
                visual_description="a massive red dragon with leathery wings and fire breath",
                substance="flesh", size_category="huge",
                tags=["LIVING", "HOSTILE", "FLYING", "HEAT_SOURCE"],
                behaviors=[
                    ObjectBehavior(
                        verb="follow", target="treasure, gold, and jewels",
                        expected_matches={"Gold Coin", "Ruby Gem"},
                        expected_non_matches={"Wooden Barrel", "Knight"},
                    ),
                    ObjectBehavior(
                        verb="destroy", target="knights and warriors",
                        target_tags=["LIVING"],
                        expected_matches={"Knight"},
                        expected_non_matches={"Gold Coin", "Ruby Gem", "Wooden Barrel"},
                    ),
                    ObjectBehavior(
                        verb="flee", target="water and ice",
                        # Nothing in the scene is water/ice — no matches expected
                        expected_non_matches={"Gold Coin", "Ruby Gem", "Wooden Barrel", "Knight"},
                    ),
                ],
            ),
            SceneObject(
                name="Gold Coin",
                visual_description="a shiny gold coin stamped with a crown",
                substance="metal", size_category="tiny", tags=["REFLECTIVE"],
            ),
            SceneObject(
                name="Ruby Gem",
                visual_description="a brilliant red ruby gemstone",
                substance="glass", size_category="tiny", tags=["REFLECTIVE", "BREAKABLE"],
            ),
            SceneObject(
                name="Wooden Barrel",
                visual_description="a plain oak barrel with iron bands",
                substance="wood", tags=["RIGID", "FLAMMABLE"],
            ),
            SceneObject(
                name="Knight",
                visual_description="an armored knight with a sword and shield",
                substance="metal", tags=["LIVING"],
            ),
        ],
    ),

    # 4. exclude_tags: protect LIVING but not HOSTILE
    Scenario(
        name="Protect the Village",
        description="Tag-filter with exclude_tags: guardian protects non-hostile living, destroys hostile",
        critical=True,
        objects=[
            SceneObject(
                name="Guardian Knight",
                visual_description="a noble knight in silver armor with a glowing shield",
                substance="metal", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="protect", target="innocent villagers",
                        target_tags=["LIVING"], exclude_tags=["HOSTILE"],
                        expected_matches={"Villager", "Child"},
                        expected_non_matches={"Goblin", "Zombie"},
                    ),
                    ObjectBehavior(
                        verb="destroy", target="hostile enemies",
                        target_tags=["HOSTILE"],
                        expected_matches={"Goblin", "Zombie"},
                        expected_non_matches={"Villager", "Child"},
                    ),
                ],
            ),
            SceneObject(
                name="Villager",
                visual_description="a simple peasant in brown clothes",
                substance="flesh", tags=["LIVING"],
            ),
            SceneObject(
                name="Child",
                visual_description="a small child in a blue tunic",
                substance="flesh", size_category="small", tags=["LIVING"],
            ),
            SceneObject(
                name="Goblin",
                visual_description="a small green goblin with a rusty dagger",
                substance="flesh", size_category="small", tags=["LIVING", "HOSTILE"],
            ),
            SceneObject(
                name="Zombie",
                visual_description="a shambling undead corpse with rotting flesh",
                substance="flesh", tags=["LIVING", "HOSTILE"],
            ),
        ],
    ),

    # 5. The canonical state problem — solved by tag-filter on HEAT_SOURCE
    Scenario(
        name="Burning Building",
        description="Tag-filter solves flammable-vs-on-fire: HEAT_SOURCE separates burning from burnable",
        critical=True,
        objects=[
            SceneObject(
                name="Firefighter",
                visual_description="a firefighter in yellow turnout gear with a hose",
                substance="flesh", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="destroy", target="fires and burning things",
                        target_tags=["HEAT_SOURCE"],
                        expected_matches={"Burning Table", "Burning Curtain"},
                        expected_non_matches={"Table", "Curtain", "Stone Wall"},
                    ),
                ],
            ),
            SceneObject(
                name="Table",
                visual_description="a wooden dining table with four legs",
                substance="wood", tags=["RIGID", "FLAMMABLE"],
            ),
            SceneObject(
                name="Burning Table",
                visual_description="a wooden dining table engulfed in flames",
                substance="wood", tags=["RIGID", "FLAMMABLE", "HEAT_SOURCE", "HOT"],
            ),
            SceneObject(
                name="Curtain",
                visual_description="a long red curtain hanging from a rod",
                substance="cloth", tags=["FLAMMABLE", "LIGHT"],
            ),
            SceneObject(
                name="Burning Curtain",
                visual_description="a red curtain engulfed in flames",
                substance="cloth", tags=["FLAMMABLE", "HEAT_SOURCE", "HOT", "LIGHT"],
            ),
            SceneObject(
                name="Stone Wall",
                visual_description="a thick stone wall",
                substance="stone", size_category="large", tags=["RIGID", "HEAVY"],
            ),
        ],
    ),

    # 6. Embedding edge case: musical instruments vs similar wood objects
    Scenario(
        name="Vague Targets",
        description="Embedding discrimination: specific targets (instruments) vs vague (interesting things)",
        critical=False,
        objects=[
            SceneObject(
                name="Curious Cat",
                visual_description="a curious orange tabby cat with wide eyes",
                substance="flesh", size_category="small", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="investigate", target="interesting things nearby",
                        # Vague target — informational only, no assertions
                    ),
                ],
            ),
            SceneObject(
                name="Musician",
                visual_description="a traveling bard with a feathered hat",
                substance="flesh", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="follow", target="musical instruments",
                        expected_matches={"Guitar"},
                        expected_non_matches={"Wooden Chair"},
                    ),
                ],
            ),
            SceneObject(
                name="Guitar",
                visual_description="a wooden acoustic guitar with steel strings",
                substance="wood", tags=["RIGID"],
            ),
            SceneObject(
                name="Wooden Chair",
                visual_description="a simple wooden chair with four legs",
                substance="wood", tags=["RIGID"],
            ),
            SceneObject(
                name="Shiny Diamond",
                visual_description="a brilliant cut diamond sparkling with light",
                substance="glass", size_category="tiny", tags=["REFLECTIVE", "BREAKABLE"],
            ),
        ],
    ),

    # 7. Stress test: multiple interacting behaviors, mixed modes
    Scenario(
        name="Ecosystem",
        description="Multi-object stress test: predator/prey, protector, mixed tag+embedding modes",
        critical=False,
        objects=[
            SceneObject(
                name="Wolf",
                visual_description="a fierce gray wolf with yellow eyes",
                substance="flesh", tags=["LIVING", "HOSTILE"],
                behaviors=[
                    ObjectBehavior(
                        verb="destroy", target="small prey animals",
                        target_tags=["LIVING"], exclude_tags=["HOSTILE"],
                        expected_matches={"Rabbit", "Sheep", "Shepherd", "Eagle"},
                        expected_non_matches={"Torch", "Grass", "Boulder"},
                    ),
                    ObjectBehavior(
                        verb="flee", target="fire",
                        target_tags=["HEAT_SOURCE"],
                        expected_matches={"Torch"},
                        expected_non_matches={"Rabbit", "Sheep", "Shepherd", "Grass", "Boulder",
                                              "Eagle"},
                    ),
                ],
            ),
            SceneObject(
                name="Rabbit",
                visual_description="a small white rabbit with pink ears",
                substance="flesh", size_category="small", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="flee", target="wolves and predators",
                        expected_matches={"Wolf"},
                        expected_non_matches={"Sheep", "Torch", "Grass", "Boulder"},
                    ),
                ],
            ),
            SceneObject(
                name="Sheep",
                visual_description="a fluffy white sheep with a round body",
                substance="flesh", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="flee", target="wolves and predators",
                        expected_matches={"Wolf"},
                        expected_non_matches={"Rabbit", "Torch", "Grass", "Boulder"},
                    ),
                ],
            ),
            SceneObject(
                name="Shepherd",
                visual_description="a shepherd in a cloak with a wooden crook",
                substance="flesh", tags=["LIVING"],
                behaviors=[
                    ObjectBehavior(
                        verb="protect", target="sheep and livestock",
                        target_tags=["LIVING"], exclude_tags=["HOSTILE"],
                        expected_matches={"Rabbit", "Sheep", "Eagle"},
                        expected_non_matches={"Wolf", "Torch", "Grass", "Boulder"},
                    ),
                ],
            ),
            SceneObject(
                name="Torch",
                visual_description="a burning wooden torch with a bright flame",
                substance="wood", tags=["HEAT_SOURCE", "HOT", "FLAMMABLE"],
            ),
            SceneObject(
                name="Grass",
                visual_description="a patch of dry grass",
                substance="wood", size_category="small", tags=["FLAMMABLE"],
            ),
            SceneObject(
                name="Boulder",
                visual_description="a large gray boulder",
                substance="stone", size_category="large", tags=["RIGID", "HEAVY"],
            ),
            SceneObject(
                name="Eagle",
                visual_description="a majestic golden eagle with a wide wingspan",
                substance="flesh", tags=["LIVING", "FLYING"],
                behaviors=[
                    ObjectBehavior(
                        verb="destroy", target="small prey animals",
                        target_tags=["LIVING"], exclude_tags=["HOSTILE", "FLYING"],
                        expected_matches={"Rabbit", "Sheep", "Shepherd"},
                        expected_non_matches={"Wolf", "Torch", "Grass", "Boulder"},
                    ),
                ],
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Embedding pipeline
# ---------------------------------------------------------------------------


async def compute_scene_embeddings(
    scenarios: list[Scenario],
) -> dict[str, list[float]]:
    """Batch-embed all identity strings and target queries across all scenarios."""
    texts: list[str] = []
    text_set: set[str] = set()

    for scenario in scenarios:
        for obj in scenario.objects:
            identity = build_identity_string(
                obj.name, obj.visual_description, obj.size_category, obj.substance,
            )
            if identity not in text_set:
                text_set.add(identity)
                texts.append(identity)

            for beh in obj.behaviors:
                if not beh.target_tags and not beh.exclude_tags:
                    query = build_target_query(beh.target)
                    if query not in text_set:
                        text_set.add(query)
                        texts.append(query)

    embeddings = await embed_texts(texts)
    return dict(zip(texts, embeddings, strict=True))


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    scenario: str
    owner: str
    behavior_desc: str
    mode: str
    target_object: str
    similarity: float
    matched: bool
    expected_match: bool | None  # None = informational only
    passed: bool | None


def run_scenario(
    scenario: Scenario,
    embedding_cache: dict[str, list[float]],
) -> list[AssertionResult]:
    results: list[AssertionResult] = []

    for obj in scenario.objects:
        for beh in obj.behaviors:
            # Get behavior embedding (only for embedding-mode behaviors)
            beh_embedding: list[float] = []
            if not beh.target_tags and not beh.exclude_tags:
                query = build_target_query(beh.target)
                beh_embedding = embedding_cache.get(query, [])

            tag_desc = ""
            if beh.target_tags:
                tag_desc += f" target_tags={beh.target_tags}"
            if beh.exclude_tags:
                tag_desc += f" exclude_tags={beh.exclude_tags}"
            beh_desc = f'{beh.verb} "{beh.target}"{tag_desc}'

            for target_obj in scenario.objects:
                if target_obj.name == obj.name:
                    continue

                identity = build_identity_string(
                    target_obj.name, target_obj.visual_description,
                    target_obj.size_category, target_obj.substance,
                )
                target_emb = embedding_cache.get(identity, [])

                matched, mode, sim = check_match(
                    target_obj.tags, beh.target_tags, beh.exclude_tags,
                    beh_embedding, target_emb,
                )

                # Determine expectation
                in_expected = target_obj.name in beh.expected_matches
                in_non_expected = target_obj.name in beh.expected_non_matches
                if in_expected:
                    expected = True
                    passed = matched
                elif in_non_expected:
                    expected = False
                    passed = not matched
                else:
                    expected = None
                    passed = None

                results.append(AssertionResult(
                    scenario=scenario.name,
                    owner=obj.name,
                    behavior_desc=beh_desc,
                    mode=mode,
                    target_object=target_obj.name,
                    similarity=sim,
                    matched=matched,
                    expected_match=expected,
                    passed=passed,
                ))

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(  # noqa: T201
    all_results: dict[str, list[AssertionResult]],
    scenarios: list[Scenario],
    embed_elapsed: float,
    num_texts: int,
) -> tuple[int, int, int, int]:
    """Print report. Returns (critical_pass, critical_fail, other_pass, other_fail)."""
    print("=" * 75)  # noqa: T201
    print("TARGETING SYSTEM VALIDATION TEST")  # noqa: T201
    print(f"Mode: tag-filter when target_tags present, "  # noqa: T201
          f"embedding (dot >= {MATCH_THRESHOLD}) otherwise")
    print(f"Embedded {num_texts} unique texts in {embed_elapsed:.3f}s")  # noqa: T201
    print("=" * 75)  # noqa: T201

    scenario_map = {s.name: s for s in scenarios}
    critical_pass = critical_fail = other_pass = other_fail = 0

    for scenario_name, results in all_results.items():
        scenario = scenario_map[scenario_name]
        tag = "CRITICAL" if scenario.critical else "non-critical"
        print(f"\n--- {scenario_name} [{tag}] ---")  # noqa: T201
        print(f"    {scenario.description}")  # noqa: T201

        # Group by owner + behavior
        groups: dict[str, list[AssertionResult]] = {}
        for r in results:
            key = f"{r.owner}: {r.behavior_desc}"
            groups.setdefault(key, []).append(r)

        for group_key, group_results in groups.items():
            mode = group_results[0].mode
            mode_label = "TAG MODE" if mode == "tag" else "EMBEDDING MODE"
            print(f"\n  {group_key} -> {mode_label}")  # noqa: T201

            if mode == "tag":
                print(f"    {'Object':<25} {'Tags':<35} {'Match':>5}  "  # noqa: T201
                      f"{'Expected':>8}  {'Result':>6}")
                print(f"    {'-' * 85}")  # noqa: T201
            else:
                print(f"    {'Object':<25} {'Sim':>7}  {'Match':>5}  "  # noqa: T201
                      f"{'Expected':>8}  {'Result':>6}")
                print(f"    {'-' * 60}")  # noqa: T201

            for r in group_results:
                match_str = "YES" if r.matched else "no"
                if r.expected_match is True:
                    exp_str = "YES"
                elif r.expected_match is False:
                    exp_str = "no"
                else:
                    exp_str = "—"

                if r.passed is True:
                    result_str = "PASS"
                elif r.passed is False:
                    result_str = "FAIL"
                else:
                    result_str = "info"

                mark = " " if r.passed is not False else "*"

                if mode == "tag":
                    target_scenario_obj = None
                    for s_obj in scenario.objects:
                        if s_obj.name == r.target_object:
                            target_scenario_obj = s_obj
                            break
                    tags_str = ", ".join(target_scenario_obj.tags) if target_scenario_obj else ""
                    print(f"  {mark} {r.target_object:<25} {tags_str:<35} "  # noqa: T201
                          f"{match_str:>5}  {exp_str:>8}  {result_str:>6}")
                else:
                    print(f"  {mark} {r.target_object:<25} {r.similarity:>7.3f}  "  # noqa: T201
                          f"{match_str:>5}  {exp_str:>8}  {result_str:>6}")

        # Scenario totals
        asserted = [r for r in results if r.passed is not None]
        s_pass = sum(1 for r in asserted if r.passed)
        s_fail = sum(1 for r in asserted if not r.passed)
        if scenario.critical:
            critical_pass += s_pass
            critical_fail += s_fail
        else:
            other_pass += s_pass
            other_fail += s_fail

        status = "PASS" if s_fail == 0 else "FAIL"
        print(f"\n  -> {scenario_name}: {s_pass}/{s_pass + s_fail} assertions "  # noqa: T201
              f"passed — {status}")

    # Summary
    print(f"\n{'=' * 75}")  # noqa: T201
    print("SUMMARY")  # noqa: T201
    print(f"{'=' * 75}")  # noqa: T201
    print(f"  {'Scenario':<35} {'Pass':>6} {'Fail':>6}  {'Status':>8}")  # noqa: T201
    print(f"  {'-' * 60}")  # noqa: T201

    for scenario_name, results in all_results.items():
        scenario = scenario_map[scenario_name]
        asserted = [r for r in results if r.passed is not None]
        s_pass = sum(1 for r in asserted if r.passed)
        s_fail = sum(1 for r in asserted if not r.passed)
        tag = " (critical)" if scenario.critical else ""
        status = "PASS" if s_fail == 0 else "FAIL"
        print(f"  {scenario_name + tag:<35} {s_pass:>6} {s_fail:>6}  "  # noqa: T201
              f"{status:>8}")

    total_pass = critical_pass + other_pass
    total_fail = critical_fail + other_fail
    print(f"\n  Critical: {critical_pass}/{critical_pass + critical_fail} passed"  # noqa: T201
          f"  |  Non-critical: {other_pass}/{other_pass + other_fail} passed"
          f"  |  Total: {total_pass}/{total_pass + total_fail}")

    if critical_fail > 0:
        print(f"\n  *** CRITICAL FAILURE: {critical_fail} assertion(s) failed "  # noqa: T201
              "in critical scenarios ***")
    else:
        print("\n  ALL CRITICAL TESTS PASSED")  # noqa: T201

    return critical_pass, critical_fail, other_pass, other_fail


# ---------------------------------------------------------------------------
# JSON save
# ---------------------------------------------------------------------------


def build_json_result(
    all_results: dict[str, list[AssertionResult]],
    scenarios: list[Scenario],
    embed_elapsed: float,
    num_texts: int,
    critical_pass: int,
    critical_fail: int,
    other_pass: int,
    other_fail: int,
) -> dict:
    scenario_map = {s.name: s for s in scenarios}
    scenario_results = []
    for name, results in all_results.items():
        scenario = scenario_map[name]
        asserted = [r for r in results if r.passed is not None]
        scenario_results.append({
            "name": name,
            "critical": scenario.critical,
            "assertions": [
                {
                    "owner": r.owner,
                    "behavior": r.behavior_desc,
                    "mode": r.mode,
                    "target": r.target_object,
                    "similarity": round(r.similarity, 4),
                    "matched": r.matched,
                    "expected": r.expected_match,
                    "passed": r.passed,
                }
                for r in results
            ],
            "pass": sum(1 for r in asserted if r.passed),
            "fail": sum(1 for r in asserted if not r.passed),
        })

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "match_threshold": MATCH_THRESHOLD,
        "unique_texts_embedded": num_texts,
        "embed_elapsed_s": round(embed_elapsed, 3),
        "critical_pass": critical_pass,
        "critical_fail": critical_fail,
        "other_pass": other_pass,
        "other_fail": other_fail,
        "scenarios": scenario_results,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _check_ollama() -> bool:
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Targeting system validation test")
    parser.add_argument("--save", action="store_true", default=True)
    parser.add_argument("--no-save", action="store_false", dest="save")
    args = parser.parse_args()

    if not _check_ollama():
        print("Error: Ollama not available at http://127.0.0.1:11434")  # noqa: T201
        print("Start it with: ollama serve")  # noqa: T201
        print("Pull model with: ollama pull qwen3-embedding:0.6b")  # noqa: T201
        sys.exit(1)

    # Batch embed all texts
    t0 = time.monotonic()
    embedding_cache = await compute_scene_embeddings(SCENARIOS)
    embed_elapsed = time.monotonic() - t0

    # Run all scenarios
    all_results: dict[str, list[AssertionResult]] = {}
    for scenario in SCENARIOS:
        all_results[scenario.name] = run_scenario(scenario, embedding_cache)

    # Report
    cp, cf, op, of_ = print_report(all_results, SCENARIOS, embed_elapsed, len(embedding_cache))

    # Save
    if args.save:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_dir = RESULTS_DIR / f"{ts}_targeting"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "result.json"
        data = build_json_result(
            all_results, SCENARIOS, embed_elapsed, len(embedding_cache), cp, cf, op, of_,
        )
        out_path.write_text(json.dumps(data, indent=2))
        print(f"\nResults saved to {out_dir}")  # noqa: T201

    sys.exit(1 if cf > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
