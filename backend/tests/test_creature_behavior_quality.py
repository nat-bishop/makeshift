"""Creature behavior quality gate (costs LLM calls, run manually).
    cd backend && uv run pytest tests/test_creature_behavior_quality.py -v -s
"""

from pathlib import Path

import pytest
import yaml

from app.engine.creature_behavior import evaluate_creature_behaviors

FIXTURES = yaml.safe_load(
    (Path(__file__).parent.parent / "evals/fixtures/v2_creature_behaviors.yaml").read_text()
)


@pytest.mark.parametrize(
    "fixture", FIXTURES[:10], ids=lambda f: f"{f['creature']}+{f['target']}"
)
async def test_creature_behavior(fixture):
    creature_bp = {"name": fixture["creature"], "mass_kg": 70, "armor": 30, "hp": 80}
    target_bp = {"name": fixture["target"], "mass_kg": 1, "armor": 10, "hp": 50}
    scene_inventory = [fixture["creature"], fixture["target"]]
    behaviors = await evaluate_creature_behaviors(creature_bp, [target_bp], scene_inventory)
    assert len(behaviors) >= 1
    b = behaviors[0]
    expected_mv = {"approach": 0, "flee": 1, "orbit": 2, "ignore": 3}[
        fixture["expected_movement"]
    ]
    assert b.movement == expected_mv, (
        f"Expected {fixture['expected_movement']}, got movement={b.movement}"
    )
