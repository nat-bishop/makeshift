"""Tests for V3 pairwise and creature engine."""

from app.cache.scene import CreatureBehavior, PairwiseResult, SceneCache
from app.engine.creature import compute_utility


class TestComputeUtility:
    def test_basic(self):
        u = compute_utility(90, 10.0, 20.0, False)
        assert u > 0

    def test_flee_multiplier(self):
        u_approach = compute_utility(90, 10.0, 20.0, False)
        u_flee = compute_utility(90, 10.0, 20.0, True)
        assert u_flee == u_approach * 1.5

    def test_distance_falloff(self):
        u_close = compute_utility(90, 2.0, 20.0, False)
        u_far = compute_utility(90, 18.0, 20.0, False)
        assert u_close > u_far

    def test_vampire_garlic_close(self):
        """Garlic at 2m, human at 5m — vampire should flee garlic."""
        garlic = compute_utility(90, 2.0, 20.0, True)
        human = compute_utility(85, 5.0, 20.0, False)
        assert garlic > human

    def test_vampire_garlic_far(self):
        """Garlic at 20m, human at 2m — vampire should approach human."""
        garlic = compute_utility(90, 20.0, 20.0, True)
        human = compute_utility(85, 2.0, 20.0, False)
        assert human > garlic

    def test_zero_distance(self):
        u = compute_utility(100, 0.0, 20.0, False)
        assert u == 100.0

    def test_zero_strength(self):
        u = compute_utility(0, 5.0, 20.0, False)
        assert u == 0.0


class TestPairwiseResult:
    def test_to_dict_roundtrip(self):
        pr = PairwiseResult(10, 20, 1, 0, 30, 0, False, True, True)
        d = pr.to_dict()
        pr2 = PairwiseResult.from_dict(d)
        assert pr2.damage_a == 10
        assert pr2.damage_b == 20
        assert pr2.state_change_a == 1
        assert pr2.force_b == 30
        assert pr2.destroy_b is True
        assert pr2.continuous is True


class TestCreatureBehavior:
    def test_to_dict_roundtrip(self):
        cb = CreatureBehavior(movement=0, strength=90, action=5, param=0)
        d = cb.to_dict()
        cb2 = CreatureBehavior.from_dict(d)
        assert cb2.movement == 0
        assert cb2.strength == 90
        assert cb2.action == 5
