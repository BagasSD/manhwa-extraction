"""
Schemas for batch page extraction processing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PageStatus(str, Enum):
    """Per-page processing status."""
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    manual_review = "manual_review"
    skipped = "skipped"


class PageBatchStatus(BaseModel):
    """Status of a single page within a batch job."""

    page_num: int
    status: PageStatus = PageStatus.pending
    attempts: int = 0
    error: str | None = None
    processing_time_ms: float | None = None


class BatchStatus(BaseModel):
    """Status of an entire batch extraction job."""

    chapter_id: str
    state: str = "idle"  # idle | running | cancelled | done | failed
    total: int = 0
    done: int = 0
    failed: int = 0
    pages: list[PageBatchStatus] = Field(default_factory=list)
    error: str | None = None

    @property
    def pending(self) -> int:
        return sum(1 for p in self.pages if p.status == PageStatus.pending)

    @property
    def processing(self) -> int:
        return sum(1 for p in self.pages if p.status == PageStatus.processing)

    def model_dump_api(self) -> dict[str, Any]:
        """Serialization helper that includes computed properties."""
        d = self.model_dump()
        d["pending"] = self.pending
        d["processing"] = self.processing
        return d


class BatchStartRequest(BaseModel):
    """Request body for starting a batch extraction job."""

    resume: bool = Field(
        default=True,
        description="If True, skip pages that already have a result file (page-NNN.json).",
    )
    force: bool = Field(
        default=False,
        description="If True, re-extract all pages regardless of existing results.",
    )
