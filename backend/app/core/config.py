"""
Application configuration.

All configurable values must come from environment variables (optionally via a
.env file). Nothing here should be hard-coded for later phases (Ollama host,
model name, etc.) -- Phase 0 only wires up the settings object and exposes it
through get_settings().
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = manhwa-context/ (two levels up from this file: app/core -> backend -> root)
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Central application settings.

    Values are read from environment variables first, falling back to the
    defaults below. A `.env` file at the backend root is also supported.
    """

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General app metadata ---
    APP_NAME: str = "Manhwa Context Extractor"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = ""

    # --- CORS (frontend dev server) ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Filesystem paths ---
    DATA_DIR: Path = PROJECT_ROOT / "data"
    CHAPTERS_DIR: Path = PROJECT_ROOT / "data" / "chapters"
    RESULTS_DIR: Path = PROJECT_ROOT / "data" / "results"
    EXPORTS_DIR: Path = PROJECT_ROOT / "data" / "exports"
    PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"

    # --- Ollama configuration ---
    OLLAMA_IS_CLOUD: bool = False
    OLLAMA_API_KEY: str | None = None
    OLLAMA_API_TOKEN: str | None = None
    OLLAMA_CLOUD_HOST: str = "https://api.ollama.com"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:31b-cloud"
    OLLAMA_THINK: bool = False
    OLLAMA_TEMPERATURE: float = 0.0
    OLLAMA_VISUAL_TOKENS: int = 1120
    OLLAMA_TIMEOUT: float = 120.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
