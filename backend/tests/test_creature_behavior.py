"""Phase B4: creature behavior evaluation tests."""

from app.engine.creature_behavior import CreatureBehavior


def test_creature_behavior_dataclass():
    cb = CreatureBehavior(target_name="donut", movement=0, strength=90, action=5, action_param=0)
    assert cb.movement == 0
    assert cb.action == 5
