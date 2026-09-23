"""Scene schema."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class Scene(BaseModel):
    """Extracted scene context and atmosphere."""

    location: str | None = Field(None, description="Setting or location of the scene")
    situation: str | None = Field(None, description="Brief summary of what is happening")
    actions: list[str] = Field(default_factory=list, description="Key visible actions occurring in the scene")
    mood: str | None = Field(None, description="Scene mood/atmosphere (e.g. tense, comedic, calm)")

    @field_validator("actions", mode="before")
    @classmethod
    def validate_actions(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v if item is not None and str(item).strip()]
        return []
