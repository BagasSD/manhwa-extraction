"""Extraction API routes for batch and single-page operations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.batch import BatchExtractRequest, BatchJobStatus
from app.models.page import PageDetail
from app.services.batch_service import BatchService
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    PageNotFoundError,
)

router = APIRouter(prefix="/chapters/{chapter_id}", tags=["extraction"])


@router.post("/extract", response_model=BatchJobStatus)
async def start_chapter_batch_extraction(
    chapter_id: str,
    payload: BatchExtractRequest | None = None,
) -> BatchJobStatus:
    """Trigger batch extraction for all or pending pages in a chapter."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    batch_service = BatchService()
    return batch_service.start_batch(chapter_id, payload)


@router.post("/extract/cancel", response_model=BatchJobStatus)
async def cancel_chapter_batch_extraction(chapter_id: str) -> BatchJobStatus:
    """Request cancellation of an active batch extraction job."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    batch_service = BatchService()
    return batch_service.cancel_batch(chapter_id)


@router.get("/extract/status", response_model=BatchJobStatus)
async def get_chapter_batch_status(chapter_id: str) -> BatchJobStatus:
    """Get the current progress and status of a chapter's batch extraction."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    batch_service = BatchService()
    return batch_service.get_batch_status(chapter_id)


@router.post("/pages/{page_num}/extract", response_model=PageDetail)
async def extract_single_page(chapter_id: str, page_num: int) -> PageDetail:
    """Extract structured context from a single chapter page."""
    batch_service = BatchService()
    try:
        return await batch_service.extract_single_page(chapter_id, page_num)
    except (ChapterNotFoundError, PageNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {exc}",
        ) from exc


@router.post("/pages/{page_num}/retry", response_model=PageDetail)
async def retry_single_page(chapter_id: str, page_num: int) -> PageDetail:
    """Retry extracting a page using alternative preprocessing and retry prompt."""
    batch_service = BatchService()
    try:
        return await batch_service.retry_single_page(chapter_id, page_num)
    except (ChapterNotFoundError, PageNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retry failed: {exc}",
        ) from exc
