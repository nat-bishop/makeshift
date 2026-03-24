from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    google_api_key: str = ""
    fal_key: str = ""
    session_budget_usd: float = 1.00
    llm_timeout_seconds: int = 15
    image_timeout_seconds: int = 30
    max_concurrent_image_requests: int = 3
    database_path: str = "data/game.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # Model configuration
    llm_model: str = "google-gla:gemini-3.1-flash-lite-preview"
    llm_temperature: float = 0.0
    image_model: str = "fal-ai/flux-pro/kontext"
    rembg_model: str = "birefnet-general"
    bg_removal_backend: Literal["local", "cloud"] = "local"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Observability (run `logfire auth` first, then set to true)
    logfire_enabled: bool = False

    model_config = {"env_file_encoding": "utf-8"}


settings = Settings()
