"""Page context schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.constants import OCR_CONFIDENCE_LEVELS
from app.schemas.character import Character
from app.schemas.scene import Scene
from app.schemas.text_region import TextRegion


class PageContext(BaseModel):
    """Normalized structured context extracted from a single manhwa page."""

    page: int = Field(1, description="Page number (1-based)")
    characters: list[Character] = Field(default_factory=list, description="Characters visible on page")
    texts: list[TextRegion] = Field(default_factory=list, description="Text and dialogue regions")
    scene: Scene = Field(default_factory=Scene, description="Overall scene context")
    visual_summary: str | None = Field(None, description="Short factual visual summary of the page")
    has_text: bool | None = Field(
        None,
        description="Model's claim that the page contains visible text (None = not reported)",
    )
    ocr_confidence: str | None = Field(
        None,
        description=f"Model-reported legibility of the page text: {OCR_CONFIDENCE_LEVELS}",
    )
    review_flags: list[str] = Field(
        default_factory=list,
        description="Suspicious-extraction warnings that survived all retries; page needs manual review",
    )

    @field_validator("has_text", mode="before")
    @classmethod
    def validate_has_text(cls, v: Any) -> bool | None:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ("true", "yes", "1"):
                return True
            if v_clean in ("false", "no", "0"):
                return False
        return None

    @field_validator("ocr_confidence", mode="before")
    @classmethod
    def validate_ocr_confidence(cls, v: Any) -> str | None:
        if not isinstance(v, str):
            return None
        v_clean = v.strip().lower()
        return v_clean if v_clean in OCR_CONFIDENCE_LEVELS else None
