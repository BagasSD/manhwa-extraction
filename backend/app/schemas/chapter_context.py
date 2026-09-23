"""Chapter context schemas for aggregated multi-page synthesis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChapterCharacterContext(BaseModel):
    """Character role and narrative summary within the chapter."""

    id: str = Field(..., description="Stable character ID (e.g. 'c1')")
    name: str | None = Field(None, description="Recognized or user-assigned name")
    description: str | None = Field(None, description="Visual or narrative description")
    role: str | None = Field(None, description="Role in chapter (e.g. protagonist, antagonist)")
    actions: list[str] = Field(default_factory=list, description="Key actions performed in chapter")


class ChapterEvent(BaseModel):
    """Significant chronological event spanning one or more pages."""

    pages: list[int] = Field(default_factory=list, description="Page range (e.g. [1, 3])")
    event: str = Field(..., description="Description of the event")
    characters_involved: list[str] = Field(
        default_factory=list, description="Character IDs participating in the event"
    )


class ChapterTransition(BaseModel):
    """Scene, location, or mood transition between pages."""

    pages: list[int] = Field(default_factory=list, description="Pages where transition occurs (e.g. [8, 9])")
    description: str = Field(..., description="Transition description")
    from_location: str | None = Field(None, description="Previous location")
    to_location: str | None = Field(None, description="New location")


class ChapterDialogue(BaseModel):
    """Important plot or thematic dialogue highlight."""

    page: int = Field(..., description="Page number where dialogue occurs")
    speaker: str | None = Field(None, description="Character ID who spoke")
    target: str | None = Field(None, description="Character ID spoken to")
    text: str = Field(..., description="Dialogue text")


class ChapterContext(BaseModel):
    """Structured chapter-level context aggregated across all pages."""

    chapter_id: str = Field(..., description="Target chapter identifier")
    title: str | None = Field(None, description="Chapter title")
    summary: str | None = Field(None, description="Concise chapter summary")
    characters: list[ChapterCharacterContext] = Field(
        default_factory=list, description="Major characters and their actions"
    )
    events: list[ChapterEvent] = Field(
        default_factory=list, description="Chronological major events"
    )
    transitions: list[ChapterTransition] = Field(
        default_factory=list, description="Scene and location transitions"
    )
    important_dialogue: list[ChapterDialogue] = Field(
        default_factory=list, description="Key dialogue highlights"
    )
