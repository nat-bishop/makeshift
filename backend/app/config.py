from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings

load_dotenv()

logger = logging.getLogger(__name__)

_PROFILES_PATH = Path(__file__).parent / "model_profiles.toml"

# Maps TOML key → Settings field name
_PROFILE_FIELD_MAP: dict[str, str] = {
    "temperature": "llm_temperature",
    "top_p": "llm_top_p",
    "top_k": "llm_top_k",
    "min_p": "llm_min_p",
    "presence_penalty": "llm_presence_penalty",
    "repetition_penalty": "llm_repetition_penalty",
    "thinking_disabled": "local_llm_thinking_disabled",
}


class Settings(BaseSettings):
    google_api_key: str = ""
    session_budget_usd: float = 1.00
    llm_timeout_seconds: int = 30
    image_timeout_seconds: int = 120
    max_concurrent_image_requests: int = 3
    database_path: str = "data/game.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # Model configuration
    llm_model: str = "google-gla:gemini-3.1-flash-lite-preview"
    llm_temperature: float = 0.7
    llm_top_p: float = 1.0
    llm_top_k: int = 20
    llm_min_p: float = 0.0
    llm_presence_penalty: float = 0.0
    llm_repetition_penalty: float = 1.0
    local_llm_url: str | None = None
    local_llm_thinking_disabled: bool = True
    local_image_url: str = "http://127.0.0.1:5100"
    local_image_model: str = "black-forest-labs/FLUX.2-klein-4B"
    local_image_steps: int = 4
    local_image_guidance_scale: float = 1.0
    sprite_cache_enabled: bool = True
    creation_cache_enabled: bool = True

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Observability (run `logfire auth` first, then set to true)
    logfire_enabled: bool = False

    @model_validator(mode="after")
    def _check_local_llm_model(self) -> Settings:
        if self.local_llm_url and ":" in self.llm_model:
            msg = (
                f"LLM_MODEL should be a bare model name (e.g. 'Qwen/Qwen3.5-7B')"
                f" when LOCAL_LLM_URL is set, got '{self.llm_model}'"
            )
            raise ValueError(msg)
        return self

    model_config = {"env_file_encoding": "utf-8"}


def _load_model_profile(model_name: str) -> dict[str, Any]:
    """Load sampling parameters for *model_name* from model_profiles.toml."""
    if not _PROFILES_PATH.exists():
        logger.warning("model_profiles_missing", extra={"path": str(_PROFILES_PATH)})
        return {}
    with _PROFILES_PATH.open("rb") as f:
        profiles = tomllib.load(f)
    if model_name in profiles:
        return dict(profiles[model_name])
    if "default" in profiles:
        logger.info(
            "model_profile_fallback",
            extra={"model": model_name, "profile": "default"},
        )
        return dict(profiles["default"])
    return {}


def _apply_profile(s: Settings) -> None:
    """Apply model profile values from TOML. Always overwrites Settings defaults."""
    profile = _load_model_profile(s.llm_model)
    if not profile:
        return
    applied: dict[str, Any] = {}
    for toml_key, field_name in _PROFILE_FIELD_MAP.items():
        if toml_key in profile:
            object.__setattr__(s, field_name, profile[toml_key])
            applied[toml_key] = profile[toml_key]
    if applied:
        logger.info(
            "model_profile_applied",
            extra={"model": s.llm_model, "values": applied},
        )


settings = Settings()
_apply_profile(settings)
