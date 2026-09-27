"""API routes for multi-chapter batch extraction."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.batch import MultiChapterExtractRequest, MultiChapterJobStatus
from app.services.multi_chapter_batch_service import (
    MultiChapterAlreadyRunningError,
    MultiChapterBatchService,
)

router = APIRouter(prefix="/multi-extract", tags=["multi-extraction"])


@router.post("", response_model=MultiChapterJobStatus)
async def start_multi_extract(payload: MultiChapterExtractRequest) -> MultiChapterJobStatus:
    """Start a sequential multi-chapter OCR job with a shared character roster."""
    if not payload.chapter_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chapter_ids must not be empty.",
        )
    service = MultiChapterBatchService()
    try:
        return service.start_multi_batch(payload)
    except MultiChapterAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/status", response_model=MultiChapterJobStatus)
async def get_multi_extract_status() -> MultiChapterJobStatus:
    """Get the current status of the multi-chapter OCR job."""
    return MultiChapterBatchService().get_status()


@router.post("/cancel", response_model=MultiChapterJobStatus)
async def cancel_multi_extract() -> MultiChapterJobStatus:
    """Cancel the currently running multi-chapter OCR job."""
    return MultiChapterBatchService().cancel()
