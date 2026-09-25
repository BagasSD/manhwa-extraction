"""
"Extract Image" API: panel detection, manual review and cropping.

Separate from the context-extraction routes (extraction.py, pages.py): these
endpoints never call Ollama and never touch page-{n}.json.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.panel import (
    CropAllResult,
    DetectPanelsRequest,
    ExtractedImage,
    PagePanels,
    PanelDetectionStatus,
    PanelUpdateRequest,
)
from app.services.chapter_service import ChapterNotFoundError, PageNotFoundError
from app.services.panel_service import PanelService, PanelsNotFoundError, PanelsNotReviewedError

router = APIRouter(prefix="/chapters/{chapter_id}", tags=["panels"])


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/detect-panels", response_model=PanelDetectionStatus)
async def detect_panels(chapter_id: str, payload: DetectPanelsRequest | None = None) -> PanelDetectionStatus:
    """Auto-detect panels (local OpenCV/NumPy) for the chapter in the background.

    Pages a human already reviewed are kept unless `overwrite_reviewed` is set.
    """
    try:
        return PanelService().start_detection(chapter_id, payload)
    except ChapterNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/detect-panels/status", response_model=PanelDetectionStatus)
async def detect_panels_status(chapter_id: str) -> PanelDetectionStatus:
    try:
        return PanelService().get_detection_status(chapter_id)
    except ChapterNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/pages/{page_num}/panels", response_model=PagePanels)
def get_page_panels(chapter_id: str, page_num: int) -> PagePanels:
    try:
        return PanelService().get_page_panels(chapter_id, page_num)
    except (ChapterNotFoundError, PageNotFoundError, PanelsNotFoundError) as exc:
        raise _not_found(exc) from exc


@router.put("/pages/{page_num}/panels", response_model=PagePanels)
def save_page_panels(chapter_id: str, page_num: int, payload: PanelUpdateRequest) -> PagePanels:
    """Save the human-adjusted boxes of a page; the page becomes `reviewed`."""
    try:
        return PanelService().save_reviewed_panels(chapter_id, page_num, [box.bbox for box in payload.panels])
    except (ChapterNotFoundError, PageNotFoundError) as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/crop-all",
    response_model=CropAllResult,
    responses={409: {"description": "Some pages are not reviewed yet; body lists them"}},
)
async def crop_all(chapter_id: str) -> CropAllResult | JSONResponse:
    """Crop every reviewed panel into data/extractedImage/{chapter_id}/.

    Returns 409 with `unreviewed_pages` while any page is not reviewed.
    """
    service = PanelService()
    try:
        return await asyncio.to_thread(service.crop_all_reviewed, chapter_id)
    except ChapterNotFoundError as exc:
        raise _not_found(exc) from exc
    except PanelsNotReviewedError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc), "unreviewed_pages": exc.unreviewed_pages},
        )


@router.get("/extracted-images", response_model=list[ExtractedImage])
def list_extracted_images(chapter_id: str) -> list[ExtractedImage]:
    try:
        return PanelService().list_extracted_images(chapter_id)
    except ChapterNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/extracted-images/{filename}")
def get_extracted_image(chapter_id: str, filename: str) -> FileResponse:
    try:
        return FileResponse(PanelService().extracted_image_path(chapter_id, filename), media_type="image/png")
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
