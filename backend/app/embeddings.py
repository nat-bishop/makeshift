"""Embedding system using Ollama's qwen3-embedding:0.6b for semantic targeting."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "qwen3-embedding:0.6b"
EMBED_DIM = 1024

# Instruction prefix for asymmetric retrieval — queries get this, documents don't.
# This is how qwen3-embedding was trained and dramatically improves discrimination.
RETRIEVAL_PREFIX = "Instruct: Retrieve objects matching this description.\nQuery: "

SIZE_PHRASES: dict[str, str] = {
    "tiny": "tiny",
    "small": "small",
    "large": "large",
    "huge": "towering and huge",
}


def build_identity_string(
    name: str,
    visual_description: str,
    size_category: str,
    substance: str,
) -> str:
    """Build a STABLE identity string for embedding. No tags — includes substance."""
    parts = [name, visual_description]
    if size_category in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size_category])
    parts.append(f"made of {substance}")
    return ", ".join(parts)


def build_target_query(target_text: str) -> str:
    """Wrap behavior target text with retrieval instruction prefix."""
    return f"{RETRIEVAL_PREFIX}{target_text}"


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
    substance: str,
    behavior_targets: list[str],
) -> tuple[list[float], list[list[float]]]:
    """Compute identity embedding + all behavior target embeddings in one batch.

    Identity string is embedded raw (document). Behavior targets get instruction
    prefix (queries) for asymmetric retrieval.
    """
    identity_str = build_identity_string(name, visual_description, size_category, substance)
    query_texts = [build_target_query(t) for t in behavior_targets]
    all_texts = [identity_str, *query_texts]
    all_embeddings = await embed_texts(all_texts)
    identity_embedding = all_embeddings[0]
    behavior_embeddings = all_embeddings[1:]
    return identity_embedding, behavior_embeddings
