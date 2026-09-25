"""Page model and metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.schemas.page_context import PageContext


class PageInfo(BaseModel):
    """Metadata describing a single page inside a chapter."""

    page_number: int = Field(..., description="1-based index of the page in reading order")
    filename: str = Field(..., description="File name of the image")
    file_path: str = Field(..., description="Absolute path to the image file")
    status: str = Field("pending", description="Processing status: pending, processing, done, failed, manual_review")
    has_raw_result: bool = Field(False, description="Whether raw AI output exists")
    has_normalized_result: bool = Field(False, description="Whether normalized/reviewed result exists")
    error_message: str | None = Field(None, description="Error message if extraction failed")
    panel_status: Literal["none", "auto_detected", "reviewed", "cropped"] = Field(
        "none", description="Extract Image state of this page"
    )
    panel_count: int = Field(0, description="Number of panel boxes on this page")


class PageDetail(PageInfo):
    """Detailed page information including extracted context if available."""

    raw_result: dict[str, Any] | None = None
    context: PageContext | None = None
