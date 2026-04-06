"""Gate dataset — fast structural validation, no LLM judges.

14 cases with unambiguous expected outputs. Run with `--gate` flag
for a quick sanity check before committing to a full eval run.
"""

from __future__ import annotations

from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator

from evals.dataset import EVAL_CASES, CaseMeta

# Cases chosen for strong, unambiguous expected outputs across categories.
# ~4 mundane, ~3 weapons, ~3 creatures, ~2 adversarial, ~2 abstract.
GATE_CASE_NAMES: frozenset[str] = frozenset({
    # Mundane — clear substance expectations
    "rock",             # stone
    "wooden chair",     # wood
    "banana",           # wood + FOOD + LIGHT
    "hot coal",         # stone + burning
    # Weapons — substance + element + tag combos
    "fire sword",       # metal + burning + SHARP + WEAPON
    "sword",            # metal + SHARP + WEAPON
    "time bomb",        # metal + EXPLOSIVE + WEAPON
    # Creatures — flesh + element + CREATURE category
    "acid spider",      # flesh + acidic + CREATURE
    "friendly dog",     # flesh + CREATURE
    "electric jellyfish",  # flesh + electric + CREATURE
    # Adversarial — typo tolerance
    "fiar swrod",       # typo: metal + burning + SHARP
    "helecopter",       # typo: metal + windy + FLYING
    # Abstract — creative mapping with clear anchors
    "the sun",          # fire substance
    "tiny black hole",  # magnetic + HEAVY
})


def build_gate_dataset(
    evaluators: list[Evaluator] | None = None,
) -> Dataset[str, str, CaseMeta]:
    """Build a Dataset containing only the gate cases."""
    cases = [c for c in EVAL_CASES if c.name in GATE_CASE_NAMES]
    return Dataset(cases=cases, evaluators=evaluators or [])
