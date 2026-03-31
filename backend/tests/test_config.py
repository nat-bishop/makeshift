from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from app.config import Settings, _apply_profile, _load_model_profile

# Env vars that load_dotenv() may have injected into the process
_LLM_ENV_VARS = [
    "LLM_MODEL", "LLM_TEMPERATURE", "LLM_TOP_P", "LLM_TOP_K", "LLM_MIN_P",
    "LLM_PRESENCE_PENALTY", "LLM_REPETITION_PENALTY", "LOCAL_LLM_URL",
    "LOCAL_LLM_THINKING_DISABLED",
]


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove LLM env vars so tests see only what they explicitly pass."""
    for var in _LLM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _settings(**kwargs: Any) -> Settings:
    """Create a Settings instance isolated from the real .env file."""
    return Settings(_env_file=None, **kwargs)


def test_load_known_model_profile():
    profile = _load_model_profile("Qwen/Qwen3.5-35B-A3B-FP8")
    assert profile["temperature"] == 0.8
    assert profile["top_k"] == 20
    assert profile["presence_penalty"] == 1.5


def test_load_unknown_model_falls_back_to_default():
    profile = _load_model_profile("some-unknown/model")
    assert profile["temperature"] == 0.7  # default section value


def test_load_missing_toml_returns_empty():
    with patch("app.config._PROFILES_PATH", Path("/nonexistent/path.toml")):
        profile = _load_model_profile("anything")
    assert profile == {}


def test_profile_applies_when_no_env_override():
    """Profile values should fill in fields not explicitly set in env."""
    s = _settings(llm_model="Qwen/Qwen3.5-35B-A3B-FP8")
    _apply_profile(s)
    assert s.llm_temperature == 0.8
    assert s.llm_top_p == 0.95
    assert s.llm_top_k == 20
    assert s.llm_min_p == 0.0
    assert s.llm_presence_penalty == 1.5
    assert s.llm_repetition_penalty == 1.0


def test_profile_always_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile value should override even if env var is set."""
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    s = _settings(llm_model="Qwen/Qwen3.5-35B-A3B-FP8")
    _apply_profile(s)
    # profile wins — env var ignored
    assert s.llm_temperature == 0.8
    assert s.llm_top_p == 0.95


def test_gemini_profile_only_sets_temperature():
    s = _settings(llm_model="google-gla:gemini-3.1-flash-lite-preview")
    _apply_profile(s)
    assert s.llm_temperature == 1.0
    # Other params keep class defaults (not in gemini profile)
    assert s.llm_top_p == 1.0
    assert s.llm_presence_penalty == 0.0
