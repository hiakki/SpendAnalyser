from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Process-wide config; override via env or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_prefix="SPENDA_",
        extra="ignore",
    )

    # storage
    db_url: str = f"sqlite:///{DATA_DIR / 'spend.db'}"
    upload_dir: str = str(DATA_DIR / "uploads")

    # llm
    llm_enabled: bool = False
    llm_provider: str = "openai"  # openai | gemini
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    gemini_api_key: str | None = None

    # categorization
    llm_min_confidence: float = 0.6
    rules_min_score: int = 2  # at least 2 keyword chars matched

    # currency
    default_currency: str = "INR"

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    return settings
