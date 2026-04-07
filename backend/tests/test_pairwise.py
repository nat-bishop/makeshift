"""Phase B3: pairwise evaluator unit tests (mock LLM)."""

from app.cache.manager import CacheManager
from app.models.pairwise import PairwiseResult


def test_pairwise_result_defaults():
    pr = PairwiseResult()
    assert pr.damage_a == 0
    assert pr.destroy_a is False
    assert pr.mode == 0


def test_pair_key_deterministic():
    assert CacheManager.pair_key("B", "A") == CacheManager.pair_key("A", "B")
