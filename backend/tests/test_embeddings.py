"""Tests for V2 embedding system."""

import math

import pytest
from app.embeddings import build_embed_string, embed_texts
from app.models.tags import Tag


class TestBuildEmbedString:
    def test_basic(self) -> None:
        s = build_embed_string("Fire Sword", "a gleaming blade", "medium", [Tag.SHARP, Tag.METALLIC])
        assert "Fire Sword" in s
        assert "a gleaming blade" in s
        assert "sharp-edged" in s
        assert "metallic" in s
        # medium size omitted
        assert "medium" not in s.split(", ")[2:]

    def test_large_size(self) -> None:
        s = build_embed_string("Boulder", "a huge rock", "large", [Tag.RIGID])
        assert "large" in s

    def test_huge_size(self) -> None:
        s = build_embed_string("Dragon", "a fire dragon", "huge", [Tag.LIVING])
        assert "towering and huge" in s

    def test_no_tags(self) -> None:
        s = build_embed_string("Rock", "a gray stone", "medium", [])
        assert s == "Rock, a gray stone"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
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
            "Donut, a glazed sugary donut with rainbow sprinkles, fragile",
            "food, especially donuts",
            "criminals and lawbreakers",
        ])
        donut_food = _cosine_sim(vecs[0], vecs[1])
        donut_criminal = _cosine_sim(vecs[0], vecs[2])
        assert donut_food > 0.5
        assert donut_criminal < 0.3

    async def test_burning_spoon(self) -> None:
        vecs = await embed_texts([
            "Wooden Spoon, a smooth cooking spoon, on fire, hot",
            "fires and burning things",
            "Wooden Spoon, a smooth cooking spoon, hard and rigid",
        ])
        burning_fire = _cosine_sim(vecs[0], vecs[1])
        plain_fire = _cosine_sim(vecs[2], vecs[1])
        assert burning_fire > plain_fire

    async def test_medusa_petrify(self) -> None:
        vecs = await embed_texts([
            "Villager, a frightened peasant, alive",
            "prey animals",
            "Villager, a frightened peasant, hard and rigid, fragile",
        ])
        alive_prey = _cosine_sim(vecs[0], vecs[1])
        stone_prey = _cosine_sim(vecs[2], vecs[1])
        assert alive_prey > stone_prey
