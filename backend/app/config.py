from typing import Literal

from pydantic_settings import BaseSettings


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
    image_model: str = "fal-ai/flux-pro/kontext"
    rembg_model: str = "birefnet-general"
    bg_removal_backend: Literal["local", "cloud"] = "local"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
