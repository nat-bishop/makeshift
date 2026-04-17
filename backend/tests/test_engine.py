"""Tests for behavior data models + utility function."""

from app.cache.scene import BehaviorEntry
from app.engine.behavior import PRIORITY_WEIGHTS, compute_utility


class TestComputeUtility:
    def test_basic(self):
        u = compute_utility(3, 10.0, 20.0, False)  # priority 3 = weight 100
        assert u > 0

    def test_flee_multiplier(self):
        u_approach = compute_utility(3, 10.0, 20.0, False)
        u_flee = compute_utility(3, 10.0, 20.0, True)
        assert u_flee == u_approach * 1.5

    def test_distance_falloff(self):
        u_close = compute_utility(3, 2.0, 20.0, False)
        u_far = compute_utility(3, 18.0, 20.0, False)
        assert u_close > u_far

    def test_vampire_garlic_close(self):
        """Garlic at 2m (priority 3), human at 5m (priority 2) — flee garlic wins."""
        garlic = compute_utility(3, 2.0, 20.0, True)
        human = compute_utility(2, 5.0, 20.0, False)
        assert garlic > human

    def test_vampire_garlic_far(self):
        """Garlic at 40m (priority 3), human at 2m (priority 2) — approach human wins."""
        garlic = compute_utility(3, 40.0, 20.0, True)
        human = compute_utility(2, 2.0, 20.0, False)
        assert human > garlic

    def test_zero_distance_max_priority(self):
        u = compute_utility(3, 0.0, 20.0, False)
        assert u == PRIORITY_WEIGHTS[3]

    def test_zero_priority(self):
        u = compute_utility(0, 5.0, 20.0, False)
        assert u == 0.0

    def test_priority_ordering(self):
        """Higher priority always wins at same distance."""
        for p in range(3):
            u_low = compute_utility(p, 10.0, 20.0, False)
            u_high = compute_utility(p + 1, 10.0, 20.0, False)
            assert u_high > u_low


class TestBehaviorEntry:
    def test_to_dict_roundtrip(self):
        be = BehaviorEntry(
            movement=0,
            priority=3,
            action=1,
            amount=80,
            state_action=1,
            state_id=2,
            delivery=1,
            projectile_name="missile",
        )
        d = be.to_dict()
        be2 = BehaviorEntry.from_dict(d)
        assert be2.movement == 0
        assert be2.priority == 3
        assert be2.action == 1
        assert be2.amount == 80
        assert be2.state_action == 1
        assert be2.state_id == 2
        assert be2.delivery == 1
        assert be2.projectile_name == "missile"

    def test_defaults(self):
        be = BehaviorEntry.from_dict({})
        assert be.movement == 2
        assert be.state_action == 0
        assert be.delivery == 0
        assert be.projectile_name == ""
