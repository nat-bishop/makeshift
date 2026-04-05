"""Tests for embedding system."""

import math

import pytest
from app.embeddings import RETRIEVAL_PREFIX, build_identity_string, build_target_query, embed_texts


class TestBuildIdentityString:
    def test_basic(self) -> None:
        s = build_identity_string("Fire Sword", "a gleaming blade", "medium", "metal")
        assert "Fire Sword" in s
        assert "a gleaming blade" in s
        assert "made of metal" in s
        # medium size omitted
        assert "medium" not in s.split(", ")[2:]

    def test_large_size(self) -> None:
        s = build_identity_string("Boulder", "a huge rock", "large", "stone")
        assert "large" in s
        assert "made of stone" in s

    def test_huge_size(self) -> None:
        s = build_identity_string("Dragon", "a fire dragon", "huge", "flesh")
        assert "towering and huge" in s

    def test_no_size_phrase_for_medium(self) -> None:
        s = build_identity_string("Rock", "a gray stone", "medium", "stone")
        assert s == "Rock, a gray stone, made of stone"

    def test_substance_included(self) -> None:
        s = build_identity_string("Table", "a wooden table", "medium", "wood")
        assert "made of wood" in s


class TestBuildTargetQuery:
    def test_prefix_applied(self) -> None:
        q = build_target_query("food, especially donuts")
        assert q.startswith(RETRIEVAL_PREFIX)
        assert "food, especially donuts" in q

    def test_empty_target(self) -> None:
        q = build_target_query("")
        assert q == f"{RETRIEVAL_PREFIX}"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@pytest.mark.skipif(True, reason="Requires Ollama with qwen3-embedding model running")
class TestEmbedTextsIntegration:
    """Integration tests requiring a running Ollama instance."""

    async def test_returns_1024_dim(self) -> None:
        vecs = await embed_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 1024

    async def test_donut_similarity(self) -> None:
        vecs = await embed_texts([
            "Donut, a glazed sugary donut with rainbow sprinkles, made of rubber",
            "food, especially donuts",
            "criminals and lawbreakers",
        ])
        donut_food = _cosine_sim(vecs[0], vecs[1])
        donut_criminal = _cosine_sim(vecs[0], vecs[2])
        assert donut_food > 0.5
        assert donut_criminal < 0.3
