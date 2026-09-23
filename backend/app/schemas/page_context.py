"""Page context schema."""

from __future__ import annotations

from pydantic import BaseModel, Field

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
