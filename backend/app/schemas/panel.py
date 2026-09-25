"""Schemas for the "Extract Image" (panel detection + crop) pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.page_context import Panel

PagePanelStatus = Literal["auto_detected", "reviewed"]


class PagePanels(BaseModel):
    """Contents of `panels/page-{n}.panels.json`: the panels of one page."""

    page: int = Field(..., ge=1)
    image_width: int = Field(..., ge=1)
    image_height: int = Field(..., ge=1)
    status: PagePanelStatus = Field(
        "auto_detected",
        description="Page-level review state; a page with zero panels can still be reviewed",
    )
    panels: list[Panel] = Field(default_factory=list)
    updated_at: str = ""
    cropped_at: str | None = Field(None, description="Set by crop-all; cleared when the boxes change")


class PanelBoxInput(BaseModel):
    """One box sent by the review UI; index and status are assigned by the server."""

    bbox: list[int]


class PanelUpdateRequest(BaseModel):
    """PUT body: the full, human-reviewed set of boxes for a page."""

    panels: list[PanelBoxInput] = Field(default_factory=list)


class DetectPanelsRequest(BaseModel):
    """POST /detect-panels body."""

    pages: list[int] | None = Field(None, description="Page numbers to detect; None = whole chapter")
    overwrite_reviewed: bool = Field(
        False, description="Also re-detect pages a human already reviewed (discards their edits)"
    )


class PanelDetectionStatus(BaseModel):
    """Progress of a chapter's panel-detection job."""

    chapter_id: str
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    total_pages: int = 0
    processed_pages: int = 0
    detected_pages: int = 0
    skipped_pages: int = Field(0, description="Reviewed pages left untouched")
    failed_pages: int = 0
    current_page: int | None = None
    message: str | None = None
    error: str | None = None


class CropAllResult(BaseModel):
    """Outcome of POST /crop-all."""

    chapter_id: str
    output_dir: str
    total_crops: int
    pages_cropped: int
    files: list[str] = Field(default_factory=list, description="File names inside output_dir")


class ExtractedImage(BaseModel):
    """One cropped panel file in data/extractedImage/{chapter_id}/."""

    filename: str
    page: int
    crop_index: int
    size_bytes: int
