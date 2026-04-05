"""Embedding-based substance/element matching eval.

Tests whether freeform LLM text (e.g., "steel", "frozen water") can be
reliably matched to the correct Substance + Element|None via cosine similarity
against pre-computed reference embeddings.

Compares four embedding strategies + an LLM baseline:
  A: Match against 112 element+substance combos only (no "none" element)
  B: Match substance (16) and element (7 + "none") independently
  C: Match against combos + bare substances (128 total, bare = no element)
  D: Independent substance match + element only if it beats "none" by a margin
  LLM: Ask the actual LLM to classify freeform text into substance+element

Requires Ollama running with qwen3-embedding:0.6b.

Usage:
    cd backend && uv run python -m evals.test_embedding_match
    cd backend && uv run python -m evals.test_embedding_match --category synonym
    cd backend && uv run python -m evals.test_embedding_match --verbose
    cd backend && uv run python -m evals.test_embedding_match --no-llm   # skip LLM baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from pydantic import BaseModel
from pydantic_ai import Agent

import app.embeddings
from app.embeddings import EMBED_MODEL, embed_texts
from app.models.substances import Element, Substance

RESULTS_DIR = Path(__file__).parent / "results"

STRATEGY_NAMES = ("A", "B", "C", "D", "LLM")

# Element confidence margin for Strategy D: best element must beat "none" by this much
ELEMENT_MARGIN = 0.05


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchCase:
    freeform: str
    expected_substance: Substance
    expected_element: Element | None = None
    category: str = ""
    notes: str = ""
    alt_substance: Substance | None = None
    alt_element: Element | None = None  # only meaningful when alt_substance is set


@dataclass
class StrategyResult:
    strategy: str
    top3: list[tuple[str, float]]
    matched_substance: str
    matched_element: str | None
    correct: bool
    soft_correct: bool
    substance_correct: bool
    element_correct: bool


# ---------------------------------------------------------------------------
# LLM baseline model
# ---------------------------------------------------------------------------


class LLMClassification(BaseModel):
    substance: Substance
    element: Element | None = None


LLM_CLASSIFY_PROMPT = """\
Given a freeform material/substance description, classify it into the best matching \
substance and optional element from the game's enum values.

Substances: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, \
slime, ice, lava, fire, smoke, flesh

Elements (pick 0 or 1): burning, electric, magnetic, freezing, acidic, toxic, windy

Only pick an element if the description implies elemental properties. \
Plain materials like "steel" or "timber" should have no element.

Respond with just the substance and element.\
"""


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

CASES: list[MatchCase] = [
    # --- Simple synonyms ---
    MatchCase("steel", Substance.METAL, category="synonym"),
    MatchCase("timber", Substance.WOOD, category="synonym"),
    MatchCase("rock", Substance.STONE, category="synonym"),
    MatchCase("magma", Substance.LAVA, category="synonym"),
    MatchCase("fabric", Substance.CLOTH, category="synonym"),
    MatchCase("goo", Substance.SLIME, category="synonym"),
    MatchCase("porcelain", Substance.CERAMIC, category="synonym"),
    MatchCase("vapor", Substance.SMOKE, category="synonym"),
    MatchCase("meat", Substance.FLESH, category="synonym"),
    MatchCase("flame", Substance.FIRE, category="synonym"),
    MatchCase("frost", Substance.ICE, category="synonym"),
    MatchCase("H2O", Substance.WATER, category="synonym"),
    MatchCase("latex", Substance.RUBBER, category="synonym"),
    MatchCase("petroleum", Substance.OIL, category="synonym"),
    MatchCase("crystal", Substance.GLASS, category="synonym",
              alt_substance=Substance.ICE, notes="could be ice crystal"),

    # --- Compositional ---
    MatchCase("burning wood", Substance.WOOD, Element.BURNING, category="compositional"),
    MatchCase("frozen water", Substance.WATER, Element.FREEZING, category="compositional",
              alt_substance=Substance.ICE, alt_element=None,
              notes="ice substance is also valid"),
    MatchCase("electrified metal", Substance.METAL, Element.ELECTRIC, category="compositional"),
    MatchCase("toxic slime", Substance.SLIME, Element.TOXIC, category="compositional"),
    MatchCase("acidic water", Substance.WATER, Element.ACIDIC, category="compositional"),
    MatchCase("magnetic metal", Substance.METAL, Element.MAGNETIC, category="compositional"),
    MatchCase("freezing stone", Substance.STONE, Element.FREEZING, category="compositional"),
    MatchCase("burning oil", Substance.OIL, Element.BURNING, category="compositional"),
    MatchCase("windy smoke", Substance.SMOKE, Element.WINDY, category="compositional"),
    MatchCase("electric glass", Substance.GLASS, Element.ELECTRIC, category="compositional"),

    # --- Ambiguous ---
    MatchCase("ice", Substance.ICE, category="ambiguous",
              alt_substance=Substance.WATER, alt_element=Element.FREEZING,
              notes="ice is both a substance and water+freezing"),
    MatchCase("lava", Substance.LAVA, category="ambiguous",
              notes="lava is a substance but could be stone+burning"),
    MatchCase("charcoal", Substance.WOOD, Element.BURNING, category="ambiguous",
              alt_substance=Substance.STONE, notes="burned wood"),
    MatchCase("steam", Substance.SMOKE, category="ambiguous",
              alt_substance=Substance.WATER, alt_element=Element.BURNING,
              notes="water vapor"),
    MatchCase("rust", Substance.METAL, Element.ACIDIC, category="ambiguous",
              notes="corroded metal"),

    # --- Creative ---
    MatchCase("plasma", Substance.FIRE, Element.ELECTRIC, category="creative"),
    MatchCase("swamp water", Substance.WATER, Element.TOXIC, category="creative"),
    MatchCase("obsidian", Substance.GLASS, category="creative",
              alt_substance=Substance.STONE, notes="volcanic glass"),
    MatchCase("quicksilver", Substance.METAL, category="creative",
              notes="mercury = liquid metal"),
    MatchCase("napalm", Substance.OIL, Element.BURNING, category="creative"),
    MatchCase("dry ice", Substance.ICE, category="creative",
              notes="frozen CO2"),
    MatchCase("lightning bolt", Substance.FIRE, Element.ELECTRIC, category="creative"),

    # --- Weird LLM outputs ---
    MatchCase("crystalline material", Substance.GLASS, category="weird",
              alt_substance=Substance.ICE),
    MatchCase("organic tissue", Substance.FLESH, category="weird"),
    MatchCase("a kind of slimy substance", Substance.SLIME, category="weird"),
    MatchCase("some sort of burning liquid", Substance.OIL, Element.BURNING, category="weird",
              alt_substance=Substance.LAVA, alt_element=None),
    MatchCase("frozen solid block", Substance.ICE, category="weird"),
    MatchCase("stretchy bouncy stuff", Substance.RUBBER, category="weird"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _batch_cosine_sim(query: np.ndarray, refs: np.ndarray) -> np.ndarray:
    """Cosine similarity of query (D,) against refs (N, D). Returns (N,)."""
    dot = refs @ query
    norms = np.linalg.norm(refs, axis=1) * np.linalg.norm(query)
    return dot / np.clip(norms, 1e-10, None)


def _check_ollama() -> bool:
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def _parse_combo_label(label: str) -> tuple[str, str | None]:
    """Parse a reference label into (substance, element|None).

    Bare substance labels like "metal" -> ("metal", None).
    Combo labels like "burning metal" -> ("metal", "burning").
    """
    substances = {s.value for s in Substance}
    elements = {e.value for e in Element}

    # Bare substance
    if label in substances:
        return label, None

    # "element substance" format
    parts = label.split(" ", 1)
    if len(parts) == 2 and parts[0] in elements and parts[1] in substances:
        return parts[1], parts[0]

    # Fallback: just return as substance with no element
    return label, None


def _matches_expected(
    matched_sub: str,
    matched_elem: str | None,
    case: MatchCase,
) -> tuple[bool, bool]:
    """Returns (exact_match, soft_match)."""
    exact = (matched_sub == case.expected_substance.value
             and matched_elem == (case.expected_element.value if case.expected_element else None))

    soft = exact
    if not exact and case.alt_substance is not None:
        alt_elem = case.alt_element.value if case.alt_element else None
        soft = (matched_sub == case.alt_substance.value and matched_elem == alt_elem)

    return exact, soft


# ---------------------------------------------------------------------------
# Matching strategies
# ---------------------------------------------------------------------------


def _run_strategy_a(
    query: np.ndarray,
    combo_refs: np.ndarray,
    combo_labels: list[str],
    case: MatchCase,
) -> StrategyResult:
    """Strategy A: combo-only (112 element+substance pairs, no bare substances)."""
    sims = _batch_cosine_sim(query, combo_refs)
    ranked = sorted(zip(combo_labels, sims.tolist()), key=lambda x: x[1], reverse=True)
    top3 = [(label, round(score, 4)) for label, score in ranked[:3]]
    sub, elem = _parse_combo_label(ranked[0][0])
    exact, soft = _matches_expected(sub, elem, case)
    return StrategyResult(
        strategy="A",
        top3=top3,
        matched_substance=sub,
        matched_element=elem,
        correct=exact,
        soft_correct=soft,
        substance_correct=sub == case.expected_substance.value,
        element_correct=elem == (case.expected_element.value if case.expected_element else None),
    )


def _run_strategy_b(
    query: np.ndarray,
    sub_refs: np.ndarray,
    sub_labels: list[str],
    elem_refs: np.ndarray,
    elem_labels: list[str],
    case: MatchCase,
) -> StrategyResult:
    """Strategy B: independent matching (16 substances + 8 elements)."""
    sub_sims = _batch_cosine_sim(query, sub_refs)
    elem_sims = _batch_cosine_sim(query, elem_refs)

    sub_ranked = sorted(zip(sub_labels, sub_sims.tolist()), key=lambda x: x[1], reverse=True)
    elem_ranked = sorted(zip(elem_labels, elem_sims.tolist()), key=lambda x: x[1], reverse=True)

    best_sub = sub_ranked[0][0]
    best_elem_label = elem_ranked[0][0]
    best_elem = None if best_elem_label == "none" else best_elem_label

    # Build combined top3 for display
    top3_sub = [(f"sub:{l}", round(s, 4)) for l, s in sub_ranked[:3]]
    top3_elem = [(f"elem:{l}", round(s, 4)) for l, s in elem_ranked[:3]]
    top3 = top3_sub + top3_elem

    exact, soft = _matches_expected(best_sub, best_elem, case)
    return StrategyResult(
        strategy="B",
        top3=top3,
        matched_substance=best_sub,
        matched_element=best_elem,
        correct=exact,
        soft_correct=soft,
        substance_correct=best_sub == case.expected_substance.value,
        element_correct=best_elem == (case.expected_element.value if case.expected_element else None),
    )


def _run_strategy_c(
    query: np.ndarray,
    full_refs: np.ndarray,
    full_labels: list[str],
    case: MatchCase,
) -> StrategyResult:
    """Strategy C: combos + bare substances (128 total)."""
    sims = _batch_cosine_sim(query, full_refs)
    ranked = sorted(zip(full_labels, sims.tolist()), key=lambda x: x[1], reverse=True)
    top3 = [(label, round(score, 4)) for label, score in ranked[:3]]
    sub, elem = _parse_combo_label(ranked[0][0])
    exact, soft = _matches_expected(sub, elem, case)
    return StrategyResult(
        strategy="C",
        top3=top3,
        matched_substance=sub,
        matched_element=elem,
        correct=exact,
        soft_correct=soft,
        substance_correct=sub == case.expected_substance.value,
        element_correct=elem == (case.expected_element.value if case.expected_element else None),
    )


def _run_strategy_d(
    query: np.ndarray,
    sub_refs: np.ndarray,
    sub_labels: list[str],
    elem_refs: np.ndarray,
    elem_labels: list[str],
    case: MatchCase,
) -> StrategyResult:
    """Strategy D: independent substance + element only if it beats 'none' by margin."""
    sub_sims = _batch_cosine_sim(query, sub_refs)
    elem_sims = _batch_cosine_sim(query, elem_refs)

    sub_ranked = sorted(zip(sub_labels, sub_sims.tolist()), key=lambda x: x[1], reverse=True)
    elem_ranked = sorted(zip(elem_labels, elem_sims.tolist()), key=lambda x: x[1], reverse=True)

    best_sub = sub_ranked[0][0]

    # Find the "none" score and the best real element score
    elem_scores = dict(elem_ranked)
    none_score = elem_scores.get("none", 0.0)
    real_elems = [(l, s) for l, s in elem_ranked if l != "none"]

    best_elem: str | None = None
    if real_elems:
        best_real_label, best_real_score = real_elems[0]
        # Only assign element if it beats "none" by the margin
        if best_real_score > none_score + ELEMENT_MARGIN:
            best_elem = best_real_label

    # Build combined top3 for display
    top3_sub = [(f"sub:{l}", round(s, 4)) for l, s in sub_ranked[:3]]
    top3_elem = [(f"elem:{l}", round(s, 4)) for l, s in elem_ranked[:3]]
    top3 = top3_sub + top3_elem

    exact, soft = _matches_expected(best_sub, best_elem, case)
    return StrategyResult(
        strategy="D",
        top3=top3,
        matched_substance=best_sub,
        matched_element=best_elem,
        correct=exact,
        soft_correct=soft,
        substance_correct=best_sub == case.expected_substance.value,
        element_correct=best_elem == (case.expected_element.value if case.expected_element else None),
    )


# ---------------------------------------------------------------------------
# LLM baseline
# ---------------------------------------------------------------------------


async def _run_llm_baseline(
    cases: list[MatchCase],
) -> dict[str, StrategyResult]:
    """Run LLM classification on all cases. Returns {freeform: StrategyResult}."""
    from app.creator.agent import _build_model

    agent: Agent[None, LLMClassification] = Agent(
        _build_model(),
        output_type=LLMClassification,
        retries=2,
        system_prompt=LLM_CLASSIFY_PROMPT,
    )

    results: dict[str, StrategyResult] = {}
    for case in cases:
        try:
            result = await agent.run(case.freeform)
            out = result.output
            matched_sub = out.substance.value
            matched_elem = out.element.value if out.element else None
        except Exception as e:
            print(f"    LLM error for '{case.freeform}': {e}")
            matched_sub = "error"
            matched_elem = None

        exact, soft = _matches_expected(matched_sub, matched_elem, case)
        results[case.freeform] = StrategyResult(
            strategy="LLM",
            top3=[(f"{matched_sub}+{matched_elem or 'none'}", 1.0)],
            matched_substance=matched_sub,
            matched_element=matched_elem,
            correct=exact,
            soft_correct=soft,
            substance_correct=matched_sub == case.expected_substance.value,
            element_correct=(
                matched_elem == (case.expected_element.value if case.expected_element else None)
            ),
        )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_eval(
    category_filter: str | None = None,
    verbose: bool = False,
    run_llm: bool = True,
) -> dict:
    cases = CASES
    if category_filter:
        cases = [c for c in cases if c.category == category_filter]
        if not cases:
            print(f"No cases for category '{category_filter}'. "
                  f"Available: {sorted({c.category for c in CASES})}")
            sys.exit(1)

    # Build reference texts
    sub_labels = [s.value for s in Substance]
    elem_labels = [e.value for e in Element] + ["none"]
    combo_labels = [f"{e.value} {s.value}" for e in Element for s in Substance]
    full_labels = combo_labels + sub_labels  # combos first, then bare substances

    # Collect all unique texts for one batch call
    all_texts: list[str] = []
    text_to_idx: dict[str, int] = {}

    def _register(text: str) -> None:
        if text not in text_to_idx:
            text_to_idx[text] = len(all_texts)
            all_texts.append(text)

    for t in sub_labels + elem_labels + combo_labels + full_labels:
        _register(t)
    for case in cases:
        _register(case.freeform)

    # Batch embed everything
    t0 = time.monotonic()
    raw_embeddings = await embed_texts(all_texts)
    embed_elapsed = time.monotonic() - t0

    # Check for zero vectors (Ollama down)
    if all(v == 0.0 for v in raw_embeddings[0]):
        print("ERROR: Got zero vectors — Ollama appears unavailable")
        sys.exit(1)

    emb = {text: np.array(raw_embeddings[text_to_idx[text]]) for text in text_to_idx}

    # Build reference matrices
    sub_refs = np.array([emb[l] for l in sub_labels])
    elem_refs = np.array([emb[l] for l in elem_labels])
    combo_refs = np.array([emb[l] for l in combo_labels])
    full_refs = np.array([emb[l] for l in full_labels])

    # Run LLM baseline if requested
    llm_results: dict[str, StrategyResult] = {}
    llm_elapsed = 0.0
    if run_llm:
        print("\nRunning LLM baseline...")
        t_llm = time.monotonic()
        llm_results = await _run_llm_baseline(cases)
        llm_elapsed = time.monotonic() - t_llm
        print(f"LLM baseline done in {llm_elapsed:.1f}s")

    # Determine which strategies are active
    active_strategies = ["A", "B", "C", "D"]
    if run_llm:
        active_strategies.append("LLM")

    # Run all strategies on all cases
    all_results: list[dict] = []
    strategy_stats: dict[str, dict[str, int]] = {
        s: {"exact": 0, "soft": 0, "sub": 0, "elem": 0}
        for s in active_strategies
    }
    category_stats: dict[str, dict[str, dict[str, int]]] = {}

    print(f"\n=== EMBEDDING MATCH EVAL ===")
    print(f"Embed model: {app.embeddings.EMBED_MODEL}")
    print(f"Embedded {len(all_texts)} unique texts in {embed_elapsed:.2f}s")
    if run_llm:
        from app.config import settings as app_settings
        print(f"LLM model: {app_settings.llm_model} ({llm_elapsed:.1f}s for {len(cases)} cases)")
    print(f"Cases: {len(cases)}, Strategy D element margin: {ELEMENT_MARGIN}")

    current_category = ""
    for case in cases:
        if case.category != current_category:
            current_category = case.category
            print(f"\n--- {current_category} ---")

        query = emb[case.freeform]
        exp_elem = case.expected_element.value if case.expected_element else "none"
        print(f'\n  "{case.freeform}" -> expected: {case.expected_substance.value} ({exp_elem})')
        if case.notes:
            print(f"    note: {case.notes}")

        case_results: dict[str, StrategyResult] = {}

        res_a = _run_strategy_a(query, combo_refs, combo_labels, case)
        res_b = _run_strategy_b(query, sub_refs, sub_labels, elem_refs, elem_labels, case)
        res_c = _run_strategy_c(query, full_refs, full_labels, case)
        res_d = _run_strategy_d(query, sub_refs, sub_labels, elem_refs, elem_labels, case)

        embed_results = [res_a, res_b, res_c, res_d]
        if run_llm and case.freeform in llm_results:
            embed_results.append(llm_results[case.freeform])

        for res in embed_results:
            case_results[res.strategy] = res
            stats = strategy_stats[res.strategy]
            if res.correct:
                stats["exact"] += 1
            if res.soft_correct:
                stats["soft"] += 1
            if res.substance_correct:
                stats["sub"] += 1
            if res.element_correct:
                stats["elem"] += 1

            cat_stats = category_stats.setdefault(
                case.category,
                {s: {"exact": 0, "soft": 0} for s in active_strategies},
            )
            if res.correct:
                cat_stats[res.strategy]["exact"] += 1
            if res.soft_correct:
                cat_stats[res.strategy]["soft"] += 1

        # Print per-case results
        display = [
            ("A (combo)", res_a),
            ("B (indep)", res_b),
            ("C (c+bare)", res_c),
            ("D (margin)", res_d),
        ]
        if "LLM" in case_results:
            display.append(("LLM", case_results["LLM"]))

        for label, res in display:
            status = "PASS" if res.correct else ("SOFT" if res.soft_correct else "MISS")
            matched = f"{res.matched_substance}"
            if res.matched_element:
                matched += f"+{res.matched_element}"

            n_top = 6 if verbose else 3
            top_str = "  ".join(f"{l} {s:.3f}" for l, s in res.top3[:n_top])
            print(f"    {label:<12} -> {matched:<25} {status:<4}  [{top_str}]")

        all_results.append({
            "freeform": case.freeform,
            "expected_substance": case.expected_substance.value,
            "expected_element": case.expected_element.value if case.expected_element else None,
            "category": case.category,
            "notes": case.notes,
            "results": {
                s: {
                    "top3": r.top3,
                    "substance": r.matched_substance,
                    "element": r.matched_element,
                    "correct": r.correct,
                    "soft_correct": r.soft_correct,
                }
                for s, r in case_results.items()
            },
        })

    # Summary
    n = len(cases)
    print(f"\n{'=' * 65}")
    print(f"{'SUMMARY':^65}")
    print(f"{'=' * 65}")
    print(f"\n{'Strategy':<14} {'Exact':>8} {'Soft':>8} {'Sub-only':>10} {'Elem-only':>10}")
    print("-" * 55)
    for s in active_strategies:
        st = strategy_stats[s]
        pct = round(st["exact"] / n * 100)
        print(f"  {s:<12} {st['exact']:>3}/{n:<4} {st['soft']:>3}/{n:<4} "
              f"{st['sub']:>5}/{n:<4} {st['elem']:>5}/{n:<4}  ({pct}%)")

    print(f"\nBy category:")
    for cat in sorted(category_stats):
        cat_n = sum(1 for c in cases if c.category == cat)
        cat_s = category_stats[cat]
        parts = "  ".join(
            f"{s}={cat_s[s]['exact']}/{cat_n}({cat_s[s]['soft']}soft)"
            for s in active_strategies
        )
        print(f"  {cat:<16} {parts}")

    if run_llm:
        print(f"\nTiming: Embedding {embed_elapsed:.2f}s vs LLM {llm_elapsed:.1f}s "
              f"({llm_elapsed / embed_elapsed:.0f}x slower)")

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "embed_model": app.embeddings.EMBED_MODEL,
        "embed_elapsed_s": round(embed_elapsed, 3),
        "llm_elapsed_s": round(llm_elapsed, 3) if run_llm else None,
        "element_margin": ELEMENT_MARGIN,
        "total_cases": n,
        "unique_texts_embedded": len(all_texts),
        "strategies": {s: strategy_stats[s] for s in active_strategies},
        "by_category": {
            cat: {s: cat_s[s] for s in active_strategies}
            for cat, cat_s in category_stats.items()
        },
        "cases": all_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Embedding substance/element match eval")
    parser.add_argument("--category", type=str, default=None, help="Filter to one category")
    parser.add_argument("--verbose", action="store_true", help="Show more top matches")
    parser.add_argument("--no-save", action="store_true", help="Skip saving results")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM baseline")
    parser.add_argument("--embed-model", type=str, default=None,
                        help="Override embedding model (e.g. qwen3-embedding:4b)")
    args = parser.parse_args()

    if args.embed_model:
        app.embeddings.EMBED_MODEL = args.embed_model

    if not _check_ollama():
        print("ERROR: Ollama not reachable at http://127.0.0.1:11434")
        print("Start Ollama and pull the embedding model first.")
        sys.exit(1)

    results = asyncio.run(run_eval(
        category_filter=args.category,
        verbose=args.verbose,
        run_llm=not args.no_llm,
    ))

    if not args.no_save:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_dir = RESULTS_DIR / f"{ts}_embedding_match"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "result.json"
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
