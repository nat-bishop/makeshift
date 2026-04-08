"""Shared fixtures for V3 LLM quality gate tests.

These tests require a running LLM backend (local or cloud).
Configure via .env: LOCAL_LLM_URL + LLM_MODEL for local, or just LLM_MODEL for cloud.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import yaml

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.creator.llm as _llm_module
from app.cache.scene import SceneCache
from app.cache.store import CacheStore
from app.config import settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Pre-flight check: is the LLM reachable?
# ---------------------------------------------------------------------------


async def _llm_health_check() -> bool:
    """Quick smoke test: can we get a single int from the LLM?"""
    try:
        result = await _llm_module.ask_int("Reply with 1. Just the number.", 0, 1, -1)
        return result != -1
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
async def _check_llm_available() -> AsyncGenerator[None, None]:
    """Skip entire session if LLM is unreachable."""
    healthy = await _llm_health_check()
    if not healthy:
        model = settings.llm_model
        url = settings.local_llm_url or "(cloud)"
        pytest.skip(
            f"LLM unreachable (model={model}, url={url}). "
            f"Start local server with `make gpu` or configure a cloud model.",
            allow_module_level=True,
        )
    yield


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def cache() -> AsyncGenerator[CacheStore, None]:
    store = await CacheStore.open(":memory:")
    yield store
    await store.close()


@pytest.fixture(scope="session")
def scene() -> SceneCache:
    return SceneCache()


@pytest.fixture(scope="session")
def interaction_pairs() -> list[dict]:
    with open(FIXTURES_DIR / "interaction_pairs.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def creature_behaviors() -> list[dict]:
    with open(FIXTURES_DIR / "creature_behaviors.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def physics_reference() -> dict:
    with open(FIXTURES_DIR / "physics_reference.yaml") as f:
        return yaml.safe_load(f)
