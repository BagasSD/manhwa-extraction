"""
Batch processing service for whole-chapter extraction.

Handles:
- Sequential queue processing of chapter pages
- Progress tracking and status polling
- Resume capability (skipping already extracted pages)
- Retry handling with PRD §13.1 3-attempt escalation
- Graceful failure handling without crashing the entire batch
- Job cancellation
- Dynamic known character propagation across pages
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.models.batch import BatchExtractRequest, BatchJobStatus
from app.models.page import PageDetail
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    PageNotFoundError,
)
from app.services.character_service import CharacterService
from app.services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)


class BatchJobState:
    """Internal mutable state for a running or recent batch job."""

    def __init__(self, chapter_id: str, total_pages: int = 0) -> None:
        self.chapter_id = chapter_id
        self.status: str = "idle"
        self.current_page: int | None = None
        self.total_pages: int = total_pages
        self.processed_pages: int = 0
        self.completed_pages: int = 0
        self.failed_pages: int = 0
        self.manual_review_pages: int = 0
        self.message: str | None = None
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.error: str | None = None
        self.cancel_requested: bool = False
        self.task: asyncio.Task[Any] | None = None

    def to_status(self) -> BatchJobStatus:
        return BatchJobStatus(
            chapter_id=self.chapter_id,
            status=self.status,  # type: ignore[arg-type]
            current_page=self.current_page,
            total_pages=self.total_pages,
            processed_pages=self.processed_pages,
            completed_pages=self.completed_pages,
            failed_pages=self.failed_pages,
            manual_review_pages=self.manual_review_pages,
            message=self.message,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )


class BatchService:
    """Singleton-style service managing chapter batch extraction operations."""

    _instance: BatchService | None = None
    _jobs: dict[str, BatchJobState] = {}

    def __new__(cls, *args: Any, **kwargs: Any) -> BatchService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs = {}
        return cls._instance

    def __init__(
        self,
        settings: Settings | None = None,
        extraction_service: ExtractionService | None = None,
        chapter_service: ChapterService | None = None,
        character_service: CharacterService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.extraction_service = extraction_service or ExtractionService(settings=self.settings)
        self.chapter_service = chapter_service or ChapterService(settings=self.settings)
        self.character_service = character_service or CharacterService(settings=self.settings)

    def get_batch_status(self, chapter_id: str) -> BatchJobStatus:
        """Get the current batch job status or construct an idle summary from disk."""
        if chapter_id in self._jobs:
            return self._jobs[chapter_id].to_status()

        # Construct status from persistent chapter metadata
        chapter = self.chapter_service.get_chapter(chapter_id)
        return BatchJobStatus(
            chapter_id=chapter_id,
            status="idle",
            total_pages=chapter.total_pages,
            processed_pages=chapter.completed_pages + chapter.failed_pages,
            completed_pages=chapter.completed_pages,
            failed_pages=chapter.failed_pages,
            manual_review_pages=chapter.failed_pages,
            message="No active batch job",
        )

    def start_batch(
        self, chapter_id: str, request: BatchExtractRequest | None = None
    ) -> BatchJobStatus:
        """Start or resume batch extraction for a chapter."""
        req = request or BatchExtractRequest()
        chapter = self.chapter_service.get_chapter(chapter_id)

        # If job is already running, return current status
        if chapter_id in self._jobs and self._jobs[chapter_id].status == "running":
            return self._jobs[chapter_id].to_status()

        job = BatchJobState(chapter_id=chapter_id, total_pages=chapter.total_pages)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()
        job.message = f"Starting batch extraction for {chapter.title}..."
        self._jobs[chapter_id] = job

        # Launch in background
        job.task = asyncio.create_task(self._run_batch_job(chapter_id, req, job))
        return job.to_status()

    def cancel_batch(self, chapter_id: str) -> BatchJobStatus:
        """Cancel an active batch extraction job."""
        if chapter_id not in self._jobs or self._jobs[chapter_id].status != "running":
            return self.get_batch_status(chapter_id)

        job = self._jobs[chapter_id]
        job.cancel_requested = True
        job.message = "Cancellation requested..."
        return job.to_status()

    async def _run_batch_job(
        self, chapter_id: str, request: BatchExtractRequest, job: BatchJobState
    ) -> None:
        """Asynchronous execution loop for batch processing."""
        try:
            chapter = self.chapter_service.get_chapter(chapter_id)
            known_characters = self.character_service.get_known_characters_dict(chapter_id)

            for page in chapter.pages:
                # Check for user cancellation
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.message = "Batch processing cancelled by user."
                    job.completed_at = datetime.now(timezone.utc).isoformat()
                    return

                page_num = page.page_number

                # 1. Skip already completed pages if requested
                if request.skip_completed and not request.force_all:
                    if page.has_normalized_result and not request.retry_failed_only:
                        job.processed_pages += 1
                        job.completed_pages += 1
                        # Update known characters from existing page data if available
                        try:
                            detail = self.chapter_service.get_page(chapter_id, page_num)
                            if detail.context:
                                for ch in detail.context.characters:
                                    if ch.id and ch.id not in known_characters:
                                        known_characters[ch.id] = ch.description or "character"
                        except Exception:
                            pass
                        continue

                # 2. If retry_failed_only, skip pages that are not failed or manual_review
                if request.retry_failed_only and page.status not in ("failed", "manual_review"):
                    job.processed_pages += 1
                    if page.has_normalized_result:
                        job.completed_pages += 1
                    continue

                # 3. Process current page
                job.current_page = page_num
                job.message = f"Processing page {page_num} of {job.total_pages}..."

                try:
                    result = await self.extraction_service.extract_page(
                        image_input=page.file_path,
                        page_num=page_num,
                        known_characters=known_characters,
                        chapter_id=chapter_id,
                        preprocess_mode="original",
                        max_retries=request.max_retries_per_page,
                    )

                    job.completed_pages += 1
                    job.processed_pages += 1

                    # Propagate new characters to downstream pages
                    for ch in result.page_context.characters:
                        if ch.id and (ch.id not in known_characters or not known_characters[ch.id]):
                            known_characters[ch.id] = ch.description or "character"

                except Exception as exc:
                    logger.error(f"Failed extraction on page {page_num} of chapter {chapter_id}: {exc}")
                    # Save error state for manual review without aborting the batch
                    self.chapter_service.save_page_error(
                        chapter_id=chapter_id,
                        page_num=page_num,
                        error_message=str(exc),
                        attempts=request.max_retries_per_page + 1,
                    )
                    job.failed_pages += 1
                    job.manual_review_pages += 1
                    job.processed_pages += 1

            if job.cancel_requested:
                job.status = "cancelled"
                job.message = "Batch processing cancelled."
            else:
                job.status = "completed"
                job.current_page = None
                job.message = (
                    f"Batch processing completed: {job.completed_pages} succeeded, "
                    f"{job.failed_pages} need manual review."
                )
            job.completed_at = datetime.now(timezone.utc).isoformat()

        except Exception as exc:
            logger.exception(f"Fatal error in batch job for chapter {chapter_id}: {exc}")
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Batch failed: {exc}"
            job.completed_at = datetime.now(timezone.utc).isoformat()

    async def extract_single_page(
        self,
        chapter_id: str,
        page_num: int,
        preprocess_mode: str = "original",
        max_retries: int = 2,
    ) -> PageDetail:
        """Extract a single page and persist results."""
        page = self.chapter_service.get_page(chapter_id, page_num)
        known_chars = self.character_service.get_known_characters_dict(chapter_id)

        try:
            await self.extraction_service.extract_page(
                image_input=page.file_path,
                page_num=page_num,
                known_characters=known_chars,
                chapter_id=chapter_id,
                preprocess_mode=preprocess_mode,
                max_retries=max_retries,
            )
            return self.chapter_service.get_page(chapter_id, page_num)
        except Exception as exc:
            self.chapter_service.save_page_error(
                chapter_id=chapter_id,
                page_num=page_num,
                error_message=str(exc),
                attempts=max_retries + 1,
            )
            raise

    async def retry_single_page(
        self,
        chapter_id: str,
        page_num: int,
        preprocess_mode: str = "enhanced",
        max_retries: int = 2,
    ) -> PageDetail:
        """Retry extracting a failed page with enhanced settings."""
        return await self.extract_single_page(
            chapter_id=chapter_id,
            page_num=page_num,
            preprocess_mode=preprocess_mode,
            max_retries=max_retries,
        )
