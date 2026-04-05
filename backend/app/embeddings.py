"""Embedding system using Ollama's qwen3-embedding:0.6b for semantic targeting."""

from __future__ import annotations

import httpx
import structlog

from app.models.tags import Tag

logger = structlog.get_logger()

OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "qwen3-embedding:0.6b"
EMBED_DIM = 1024

TAG_PHRASES: dict[Tag, str] = {
    # LLM-visible tags
    Tag.SHARP: "sharp-edged",
    Tag.HEAVY: "very heavy",
    Tag.LIGHT: "lightweight",
    Tag.BOUNCY: "bouncy and elastic",
    Tag.BREAKABLE: "fragile",
    Tag.STICKY: "sticky",
    Tag.REFLECTIVE: "shiny",
    Tag.EXPLOSIVE: "explosive",
    Tag.FLYING: "flying",
    Tag.LIVING: "alive",
    Tag.WET: "wet and soaked",
    Tag.HOSTILE: "hostile",
    # Substance-derived
    Tag.RIGID: "hard and rigid",
    Tag.METALLIC: "metallic",
    Tag.INSULATING: "insulating",
    Tag.FLAMMABLE: "flammable",
    Tag.LIQUID: "liquid",
    Tag.GAS: "gaseous",
    Tag.FROZEN: "frozen solid",
    Tag.MOLTEN: "molten",
    # Element-derived
    Tag.HEAT_SOURCE: "on fire",
    Tag.HOT: "hot",
    Tag.ELECTRIC: "electrified",
    Tag.MAGNETIC: "magnetic",
    Tag.COLD: "freezing cold",
    Tag.ACIDIC: "corrosive",
    Tag.TOXIC: "poisonous",
    Tag.WIND_SOURCE: "generating wind",
    # Internal (added by rules)
    Tag.BRITTLE: "brittle",
    Tag.CORRODED: "corroded",
    Tag.GLOWING: "glowing",
}

SIZE_PHRASES: dict[str, str] = {
    "tiny": "tiny",
    "small": "small",
    "large": "large",
    "huge": "towering and huge",
}


def build_embed_string(
    name: str,
    visual_description: str,
    size_category: str,
    current_tags: list[Tag],
) -> str:
    """Build a natural-language identity string for embedding."""
    parts = [name, visual_description]
    if size_category in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size_category])
    parts.extend(
        TAG_PHRASES[t] for t in sorted(current_tags, key=lambda t: t.value)
        if t in TAG_PHRASES
    )
    return ", ".join(parts)


_ollama_client: httpx.AsyncClient | None = None


def _get_ollama_client() -> httpx.AsyncClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = httpx.AsyncClient(timeout=30.0)
    return _ollama_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via Ollama. Returns 1024-dim vectors.

    If Ollama is unavailable, returns zero vectors (behaviors degrade to nearest targeting).
    """
    if not texts:
        return []
    try:
        client = _get_ollama_client()
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings: list[list[float]] = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            logger.warning(
                "embed_count_mismatch",
                expected=len(texts),
                got=len(embeddings),
            )
            return [[0.0] * EMBED_DIM for _ in texts]
        return embeddings
    except Exception as e:
        logger.warning("embed_failed", error=str(e))
        return [[0.0] * EMBED_DIM for _ in texts]


async def compute_object_embeddings(
    name: str,
    visual_description: str,
    size_category: str,
    tags: list[Tag],
    behavior_targets: list[str],
) -> tuple[list[float], list[list[float]]]:
    """Compute identity embedding + all behavior target embeddings in one batch."""
    identity_str = build_embed_string(name, visual_description, size_category, tags)
    all_texts = [identity_str, *behavior_targets]
    all_embeddings = await embed_texts(all_texts)
    identity_embedding = all_embeddings[0]
    behavior_embeddings = all_embeddings[1:]
    return identity_embedding, behavior_embeddings
