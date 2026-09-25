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
    # Cropped panels from the "Extract Image" pipeline, one folder per chapter
    EXTRACTED_IMAGE_DIR: Path = PROJECT_ROOT / "data" / "extractedImage"
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

    # --- Page extraction strategy (docs/text-extraction-upgrade-plan-v2.md) ---
    # Default preprocessing for batch/single-page extraction. "tiled" splits tall
    # pages into upscaled vertical segments; only make it the default after the
    # benchmark shows it captures more text (PRD §15).
    EXTRACTION_PREPROCESS_MODE: str = "original"
    # Send the output JSON schema as Ollama `format` (structured outputs) instead
    # of plain "json" mode, so the model cannot invent its own key names.
    EXTRACTION_STRUCTURED_OUTPUT: bool = True
    # Structured extraction is kept near-deterministic regardless of the global
    # OLLAMA_TEMPERATURE.
    EXTRACTION_MAX_TEMPERATURE: float = 0.2
    # "tiled" preprocessing: cap on segments per page and the minimum segment
    # width (narrower segments are upscaled, at most 3x).
    EXTRACTION_TILE_MAX_SEGMENTS: int = 8
    EXTRACTION_TILE_MIN_WIDTH: int = 1024

    # --- Downstream output ---
    # Text types left out of the TXT/JSON exports and the chapter-context input
    # (sound effects such as "슈욱" are noise for the external script writer).
    # They are still extracted, stored and editable in the review UI; changing
    # a region's type there brings it back. Env format: ["sfx"]; [] keeps all.
    EXPORT_EXCLUDED_TEXT_TYPES: list[str] = ["sfx"]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
