"""Text region schema."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator

from app.core.constants import TEXT_REGION_TYPES


class TextRegion(BaseModel):
    """Extracted text/dialogue/narration region on a page."""

    id: str = Field("t1", description="Unique text identifier (e.g. 't1', 't2')")
    text: str = Field(..., description="Visible transcribed text")
    type: str = Field("speech", description=f"Region type: {TEXT_REGION_TYPES}")
    speaker: str | None = Field(None, description="Character ID speaking or emitting this text (e.g. 'c1')")
    target: str | None = Field(None, description="Character ID to whom speech is directed (e.g. 'c2')")
    bbox: list[int] | None = Field(None, description="Bounding box [ymin, xmin, ymax, xmax] or [x, y, w, h]")
    order: int = Field(1, description="Reading order sequence on the page (1-based index)")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: Any) -> str:
        if not v or not isinstance(v, str):
            return "unknown"
        v_clean = v.strip().lower()
        type_mapping = {
            "speech": "speech",
            "sp": "speech",
            "dialogue": "speech",
            "thought": "thought",
            "th": "thought",
            "narration": "narration",
            "na": "narration",
            "caption": "caption",
            "ca": "caption",
            "system": "system",
            "ui": "system",
            "sfx": "sfx",
            "sx": "sfx",
            "sound": "sfx",
            "sign": "sign",
            "unknown": "unknown",
            "uk": "unknown",
        }
        mapped = type_mapping.get(v_clean)
        if mapped:
            return mapped
        if v_clean in TEXT_REGION_TYPES:
            return v_clean
        return "unknown"

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v: Any) -> float | None:
        if v is None or v == "":
            return None
        try:
            val = float(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Confidence must be a number between 0 and 1, got {v}") from exc
        if val < 0.0 or val > 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {val}")
        return val

    @field_validator("bbox", mode="before")
    @classmethod
    def validate_bbox(cls, v: Any) -> list[int] | None:
        if v is None:
            return None
        if not isinstance(v, (list, tuple)):
            raise ValueError("Bounding box must be a list or tuple of 4 integers")
        if len(v) != 4:
            raise ValueError(f"Bounding box must contain exactly 4 numbers, got {len(v)}")
        try:
            return [int(round(x)) for x in v]
        except (ValueError, TypeError) as exc:
            raise ValueError("Bounding box coordinates must be integers") from exc
