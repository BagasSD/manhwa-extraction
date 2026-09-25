"""Chapter data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.models.page import PageInfo


class ChapterCreate(BaseModel):
    """Payload to create or register a new chapter."""

    id: str | None = Field(None, description="Unique chapter identifier (e.g. 'chapter-001'). Generated if omitted.")
    title: str = Field(..., description="Display title for the chapter")
    source_path: str = Field(..., description="Filesystem directory containing chapter page images")


class ChapterDownloadRequest(BaseModel):
    """Payload to download and register a chapter from a web URL."""

    url: str = Field(..., description="Web URL to chapter page, zip file, or direct image")
    title: str | None = Field(None, description="Optional chapter title (auto-detected if omitted)")
    id: str | None = Field(None, description="Optional custom chapter identifier slug")
    custom_headers: dict[str, str] | None = Field(None, description="Optional custom HTTP headers")



class ChapterSummary(BaseModel):
    """Summary of chapter information and progress."""

    id: str = Field(..., description="Unique chapter identifier")
    title: str = Field(..., description="Display title")
    source_path: str = Field(..., description="Path to folder containing source images")
    total_pages: int = Field(0, description="Total number of discovered pages")
    completed_pages: int = Field(0, description="Number of successfully extracted pages")
    failed_pages: int = Field(0, description="Number of failed pages")
    # Two independent pipelines (docs/plan-fitur-panel-crop.md §1.3)
    context_status: Literal["not_started", "extracting", "done"] = Field(
        "not_started", description="Context extraction (Gemma): not_started, extracting (partial), done"
    )
    image_status: Literal["not_started", "detecting", "reviewing", "cropped"] = Field(
        "not_started",
        description="Extract Image: not_started, detecting (some pages lack panels), reviewing, cropped",
    )
    panel_detected_pages: int = Field(0, description="Pages with panel data")
    panel_reviewed_pages: int = Field(0, description="Pages whose panels a human reviewed")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Chapter(ChapterSummary):
    """Full chapter model including page list."""

    pages: list[PageInfo] = Field(default_factory=list, description="Ordered list of pages in the chapter")
