"""
Multi-chapter batch extraction service.

Runs OCR sequentially across multiple chapters in order, propagating a single
growing `known_characters` dictionary across chapter boundaries so character IDs
remain consistent throughout the series.

After processing each chapter the accumulated roster is written back to that
chapter's characters.json so individual chapter roster views stay accurate.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time

from app.core.config import Settings, get_settings
from app.models.batch import MultiChapterExtractRequest, MultiChapterJobStatus
from app.services.chapter_service import ChapterNotFoundError, ChapterService
from app.services.character_service import CharacterService
from app.services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)


class MultiChapterAlreadyRunningError(Exception):
    """Raised when a multi-chapter job is already running."""


class _MultiChapterJobState:
    """Internal mutable state for a running or completed multi-chapter job."""

    def __init__(self, job_id: str, request: MultiChapterExtractRequest) -> None:
        self.job_id = job_id
        self.chapter_ids = list(request.chapter_ids)
        self.status: str = "running"
        self.current_chapter_id: str | None = None
        self.current_chapter_index: int = 0
        self.total_chapters: int = len(request.chapter_ids)
        self.current_page: int | None = None
        self.total_pages_current_chapter: int = 0
        self.processed_chapters: int = 0
        self.completed_chapters: int = 0
        self.failed_chapters: int = 0
        self.total_pages_processed: int = 0
        self.total_pages_completed: int = 0
        self.message: str | None = None
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None
        self.error: str | None = None
        self.cancel_requested: bool = False
        self.task: asyncio.Task | None = None

    def to_status(self) -> MultiChapterJobStatus:
        return MultiChapterJobStatus(
            job_id=self.job_id,
            status=self.status,  # type: ignore[arg-type]
            chapter_ids=self.chapter_ids,
            current_chapter_id=self.current_chapter_id,
            current_chapter_index=self.current_chapter_index,
            total_chapters=self.total_chapters,
            current_page=self.current_page,
            total_pages_current_chapter=self.total_pages_current_chapter,
            processed_chapters=self.processed_chapters,
            completed_chapters=self.completed_chapters,
            failed_chapters=self.failed_chapters,
            total_pages_processed=self.total_pages_processed,
            total_pages_completed=self.total_pages_completed,
            message=self.message,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
        )


class MultiChapterBatchService:
    """Service to run OCR across multiple chapters sequentially with shared character context."""

    # Module-level singleton job slot — one multi-chapter job at a time
    _current_job: _MultiChapterJobState | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.chapter_service = ChapterService(settings=self.settings)
        self.character_service = CharacterService(settings=self.settings)
        self.extraction_service = ExtractionService(settings=self.settings)

    # ── Public API ──────────────────────────────────────────────────────────

    def get_status(self) -> MultiChapterJobStatus:
        """Return current job status (idle placeholder if no job has run yet)."""
        job = MultiChapterBatchService._current_job
        if job is None:
            return MultiChapterJobStatus(
                job_id="none",
                status="idle",
                chapter_ids=[],
                total_chapters=0,
                message="No multi-chapter job has been started.",
            )
        return job.to_status()

    def start_multi_batch(self, request: MultiChapterExtractRequest) -> MultiChapterJobStatus:
        """Start a new sequential multi-chapter OCR job.

        Raises MultiChapterAlreadyRunningError if a job is currently running.
        """
        current = MultiChapterBatchService._current_job
        if current is not None and current.status == "running":
            raise MultiChapterAlreadyRunningError(
                "A multi-chapter OCR job is already running. Cancel it before starting a new one."
            )

        job_id = f"multi-{int(time.time())}"
        job = _MultiChapterJobState(job_id=job_id, request=request)
        MultiChapterBatchService._current_job = job

        job.task = asyncio.create_task(self._run(request, job))
        return job.to_status()

    def cancel(self) -> MultiChapterJobStatus:
        """Request cancellation of the currently running job."""
        job = MultiChapterBatchService._current_job
        if job is None or job.status != "running":
            return self.get_status()
        job.cancel_requested = True
        job.message = "Cancellation requested — stopping after current page…"
        return job.to_status()

    # ── Internal execution loop ─────────────────────────────────────────────

    async def _run(self, request: MultiChapterExtractRequest, job: _MultiChapterJobState) -> None:
        """Execute the multi-chapter batch loop."""
        # Shared character dictionary accumulated across all chapters
        shared_known: dict[str, str] = {}

        try:
            for idx, chapter_id in enumerate(request.chapter_ids):
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.message = "Job cancelled before processing chapter."
                    job.completed_at = datetime.now(timezone.utc).isoformat()
                    return

                job.current_chapter_index = idx
                job.current_chapter_id = chapter_id

                try:
                    chapter = self.chapter_service.get_chapter(chapter_id)
                except ChapterNotFoundError:
                    logger.warning(f"Multi-batch: chapter '{chapter_id}' not found — skipping.")
                    job.failed_chapters += 1
                    job.processed_chapters += 1
                    continue

                job.total_pages_current_chapter = chapter.total_pages
                job.message = (
                    f"Processing chapter {idx + 1}/{job.total_chapters}: {chapter.title}"
                )
                logger.info(f"Multi-batch: starting chapter '{chapter_id}' ({chapter.title})")

                # Seed shared dict with this chapter's existing roster so prior
                # manual renames/merges are preserved as starting context.
                existing = self.character_service.get_known_characters_dict(chapter_id)
                for cid, desc in existing.items():
                    if cid not in shared_known:
                        shared_known[cid] = desc

                chapter_failed = False

                for page in chapter.pages:
                    # Respect cancellation at page boundary
                    if job.cancel_requested:
                        job.status = "cancelled"
                        job.message = (
                            f"Cancelled during chapter '{chapter.title}' "
                            f"at page {page.page_number}."
                        )
                        # Still save what we have so far
                        self._save_shared_roster_to_chapters(request.chapter_ids[:idx + 1], shared_known)
                        job.completed_at = datetime.now(timezone.utc).isoformat()
                        return

                    page_num = page.page_number

                    # Skip already-completed pages unless force_all is set
                    if request.skip_completed and not request.force_all:
                        if page.has_normalized_result:
                            # Still pull characters from existing result into shared dict
                            try:
                                detail = self.chapter_service.get_page(chapter_id, page_num)
                                if detail.context:
                                    for ch in detail.context.characters:
                                        if ch.id and ch.id not in shared_known:
                                            shared_known[ch.id] = ch.description or "character"
                            except Exception:
                                pass
                            job.total_pages_processed += 1
                            job.total_pages_completed += 1
                            continue

                    job.current_page = page_num
                    job.message = (
                        f"Chapter {idx + 1}/{job.total_chapters} '{chapter.title}' "
                        f"— page {page_num}/{chapter.total_pages}"
                    )

                    try:
                        result = await self.extraction_service.extract_page(
                            image_input=page.file_path,
                            page_num=page_num,
                            known_characters=shared_known,
                            chapter_id=chapter_id,
                            preprocess_mode=self.settings.EXTRACTION_PREPROCESS_MODE,
                            max_retries=request.max_retries_per_page,
                        )

                        job.total_pages_completed += 1

                        # Propagate new characters to shared dict for all future pages/chapters
                        for ch in result.page_context.characters:
                            if ch.id and (ch.id not in shared_known or not shared_known[ch.id]):
                                shared_known[ch.id] = ch.description or "character"

                    except Exception as exc:
                        logger.error(
                            f"Multi-batch: failed page {page_num} of chapter '{chapter_id}': {exc}"
                        )
                        self.chapter_service.save_page_error(
                            chapter_id=chapter_id,
                            page_num=page_num,
                            error_message=str(exc),
                            attempts=request.max_retries_per_page + 1,
                        )
                        chapter_failed = True

                    job.total_pages_processed += 1

                job.current_page = None

                # Save the accumulated shared roster back to this chapter
                try:
                    self.character_service.save_roster_from_dict(chapter_id, shared_known)
                except Exception as exc:
                    logger.warning(f"Multi-batch: failed to save roster for chapter '{chapter_id}': {exc}")

                if chapter_failed:
                    job.failed_chapters += 1
                else:
                    job.completed_chapters += 1
                job.processed_chapters += 1

            # All chapters done — propagate final roster back to ALL participating chapters
            self._save_shared_roster_to_chapters(request.chapter_ids, shared_known)

            job.status = "completed"
            job.current_chapter_id = None
            job.message = (
                f"Bulk OCR complete: {job.completed_chapters}/{job.total_chapters} chapters "
                f"succeeded, {job.total_pages_completed} pages extracted."
            )
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Multi-batch job '{job.job_id}' completed successfully.")

        except Exception as exc:
            logger.exception(f"Fatal error in multi-chapter batch job '{job.job_id}': {exc}")
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Fatal error: {exc}"
            job.completed_at = datetime.now(timezone.utc).isoformat()

    def _save_shared_roster_to_chapters(
        self, chapter_ids: list[str], shared_known: dict[str, str]
    ) -> None:
        """Save the shared known_characters dict to each chapter's characters.json."""
        for chapter_id in chapter_ids:
            try:
                self.character_service.save_roster_from_dict(chapter_id, shared_known)
            except Exception as exc:
                logger.warning(
                    f"Multi-batch: could not save roster to chapter '{chapter_id}': {exc}"
                )
