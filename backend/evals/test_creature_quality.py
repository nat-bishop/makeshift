"""Creature quality gate: does evaluate_creature_behaviors() produce correct movement/action?

Loads creature_behaviors.yaml, builds minimal blueprints, and validates
movement, action, and param fields against fixture expectations.

Grouped by creature to minimize LLM calls (one evaluate_creature_behaviors()
call per creature with all its targets).

Run: make eval-creature
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest
import yaml
from app.cache.scene import SceneCache
from app.engine.creature import evaluate_creature_behaviors

from evals.helpers import make_blueprint

# ---------------------------------------------------------------------------
# Load and group fixture data
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "creature_behaviors.yaml"
with open(_FIXTURE_PATH) as _f:
    _RAW_DATA: list[dict] = yaml.safe_load(_f)

# Group by creature: {creature_name: [(target_name, expected_dict, note), ...]}
_GROUPED: dict[str, list[tuple[str, dict, str]]] = defaultdict(list)
for _entry in _RAW_DATA:
    _GROUPED[_entry["creature"]].append(
        (_entry["target"], _entry["expected"], _entry.get("note", ""))
    )

_CREATURE_IDS = list(_GROUPED.keys())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("creature_name", _CREATURE_IDS)
async def test_creature_behaviors(
    creature_name: str,
    scene: SceneCache,
) -> None:
    """Validate creature behaviors for all targets of a single creature."""
    entries = _GROUPED[creature_name]

    # Build creature blueprint (autonomous=True required)
    creature_bp = make_blueprint(creature_name, autonomous=True)

    # Build target blueprints
    target_bps = [make_blueprint(target_name) for target_name, _, _ in entries]
    target_names = [t.name for t in target_bps]

    # Evaluate all targets in one call
    results = await evaluate_creature_behaviors(
        creature=creature_bp,
        targets=target_bps,
        scene_inventory=target_names,
        scene=scene,
    )

    # Validate each target's behavior
    for target_name, expected, note in entries:
        assert target_name in results, (
            f"{creature_name} vs {target_name}: no result returned"
        )
        behavior = results[target_name]

        # Movement (always specified)
        if "movement" in expected:
            assert behavior.movement == expected["movement"], (
                f"{creature_name} vs {target_name}: movement={behavior.movement}, "
                f"expected {expected['movement']} ({note})"
            )

        # Action (only specified for approach/orbit creatures)
        if "action" in expected:
            assert behavior.action == expected["action"], (
                f"{creature_name} vs {target_name}: action={behavior.action}, "
                f"expected {expected['action']} ({note})"
            )

        # Param (only specified for actions needing params: damage, heal, add/remove state)
        if "param" in expected:
            assert behavior.param == expected["param"], (
                f"{creature_name} vs {target_name}: param={behavior.param}, "
                f"expected {expected['param']} ({note})"
            )
