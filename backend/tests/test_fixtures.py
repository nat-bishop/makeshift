"""Validate V2 ground truth fixtures are parseable and non-empty."""

import json
from pathlib import Path

import yaml

FIXTURE_DIR = Path(__file__).parent.parent / "evals" / "fixtures"


def test_interaction_pairs():
    data = json.loads((FIXTURE_DIR / "v2_interaction_pairs.json").read_text())
    assert len(data) == 56
    assert all("rule_id" in r for r in data)


def test_substance_physics():
    data = json.loads((FIXTURE_DIR / "v2_substance_physics.json").read_text())
    assert len(data) == 16
    assert "metal" in data


def test_creature_behaviors():
    data = yaml.safe_load((FIXTURE_DIR / "v2_creature_behaviors.yaml").read_text())
    assert len(data) >= 15
    assert all("creature" in e and "target" in e for e in data)
