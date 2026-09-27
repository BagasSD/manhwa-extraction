"""Batch extraction models and schemas."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class BatchExtractRequest(BaseModel):
    """Payload to configure batch extraction execution."""

    skip_completed: bool = Field(True, description="Skip pages that already have extracted results")
    force_all: bool = Field(False, description="Force re-extraction of all pages even if completed")
    retry_failed_only: bool = Field(False, description="Only extract/retry pages marked as failed or manual_review")
    max_retries_per_page: int = Field(2, description="Max retry attempts on schema or model error per page")


class BatchJobStatus(BaseModel):
    """Current execution status of a batch extraction job."""

    chapter_id: str = Field(..., description="Target chapter identifier")
    status: Literal["idle", "running", "completed", "cancelled", "failed"] = Field(
        "idle", description="Current execution state"
    )
    current_page: int | None = Field(None, description="Page number currently being processed")
    total_pages: int = Field(0, description="Total number of pages in chapter")
    processed_pages: int = Field(0, description="Total pages processed so far (including skipped)")
    completed_pages: int = Field(0, description="Successfully extracted pages")
    failed_pages: int = Field(0, description="Pages that failed extraction and need manual review")
    manual_review_pages: int = Field(0, description="Pages designated for manual review")
    message: str | None = Field(None, description="Status summary or last error message")
    started_at: str | None = Field(None, description="ISO timestamp when batch started")
    completed_at: str | None = Field(None, description="ISO timestamp when batch finished")
    error: str | None = Field(None, description="Global fatal error if job failed")


class MultiChapterExtractRequest(BaseModel):
    """Payload to run OCR sequentially across multiple chapters with a shared character roster."""

    chapter_ids: list[str] = Field(..., description="Ordered list of chapter IDs to process")
    skip_completed: bool = Field(True, description="Skip pages that already have extracted results")
    force_all: bool = Field(False, description="Force re-extraction of all pages even if completed")
    max_retries_per_page: int = Field(2, description="Max retry attempts on schema or model error per page")


class MultiChapterJobStatus(BaseModel):
    """Status of a sequential multi-chapter batch extraction job."""

    job_id: str = Field(..., description="Unique job identifier")
    status: Literal["idle", "running", "completed", "cancelled", "failed"] = Field(
        "idle", description="Current execution state"
    )
    chapter_ids: list[str] = Field(default_factory=list, description="All chapters in the job")
    current_chapter_id: str | None = Field(None, description="Chapter currently being processed")
    current_chapter_index: int = Field(0, description="0-based index of the current chapter")
    total_chapters: int = Field(0, description="Total number of chapters in the job")
    current_page: int | None = Field(None, description="Page number currently being processed")
    total_pages_current_chapter: int = Field(0, description="Total pages in the current chapter")
    processed_chapters: int = Field(0, description="Number of chapters fully processed")
    completed_chapters: int = Field(0, description="Number of chapters successfully completed")
    failed_chapters: int = Field(0, description="Number of chapters that had fatal errors")
    total_pages_processed: int = Field(0, description="Total pages processed across all chapters")
    total_pages_completed: int = Field(0, description="Total pages successfully extracted")
    message: str | None = Field(None, description="Status summary or last error message")
    started_at: str | None = Field(None, description="ISO timestamp when job started")
    completed_at: str | None = Field(None, description="ISO timestamp when job finished")
    error: str | None = Field(None, description="Fatal error message if job failed")
