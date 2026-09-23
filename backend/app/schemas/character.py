"""Character schema."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class Character(BaseModel):
    """Extracted character information on a page."""

    id: str = Field(..., description="Character identifier (e.g. 'c1', 'c2')")
    description: str | None = Field(None, description="Visual description of the character")
    bbox: list[int] | None = Field(None, description="Bounding box [ymin, xmin, ymax, xmax] or [x, y, w, h]")
    expression: str | None = Field(None, description="Facial expression")
    emotion: str | None = Field(None, description="Perceived emotion")
    action: str | None = Field(None, description="Current action performed by the character")

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


class KnownCharacter(BaseModel):
    """Aggregated character tracking information across chapter pages."""

    id: str = Field(..., description="Canonical character ID (e.g. 'c1')")
    name: str | None = Field(None, description="Optional canonical or user-assigned name")
    description: str | None = Field(None, description="Visual description of the character")
    first_seen_page: int = Field(1, description="First page index where character was detected")
    occurrences: int = Field(1, description="Total number of pages where this character appears")
    pages: list[int] = Field(default_factory=list, description="List of page numbers where character appears")


class CharacterRenameRequest(BaseModel):
    """Payload to rename a character ID across all chapter pages."""

    old_id: str = Field(..., description="Existing character ID to rename")
    new_id: str = Field(..., description="New character ID to assign")
    name: str | None = Field(None, description="Optional character name override")
    description: str | None = Field(None, description="Optional updated description")


class CharacterMergeRequest(BaseModel):
    """Payload to merge two character IDs across all chapter pages."""

    source_id: str = Field(..., description="Character ID to be merged away")
    target_id: str = Field(..., description="Target character ID that absorbs source_id")
    description: str | None = Field(None, description="Optional merged description override")
