"""Tests for V3 pairwise and creature engine."""

from app.cache.scene import CreatureBehavior, PairwiseResult
from app.engine.creature import PRIORITY_WEIGHTS, compute_utility


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


class TestPairwiseResult:
    def test_to_dict_roundtrip(self):
        pr = PairwiseResult(10, 20, 1, 0, 30, True)
        d = pr.to_dict()
        pr2 = PairwiseResult.from_dict(d)
        assert pr2.damage_a == 10
        assert pr2.damage_b == 20
        assert pr2.state_change_a == 1
        assert pr2.force_b == 30
        assert pr2.continuous is True


class TestCreatureBehavior:
    def test_to_dict_roundtrip(self):
        cb = CreatureBehavior(movement=0, priority=3, action=5, amount=0, state_id=0)
        d = cb.to_dict()
        cb2 = CreatureBehavior.from_dict(d)
        assert cb2.movement == 0
        assert cb2.priority == 3
        assert cb2.action == 5
