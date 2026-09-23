"""Page API routes."""

from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.models.chapter import Chapter
from app.models.page import PageDetail, PageInfo
from app.schemas.page_context import PageContext
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    PageNotFoundError,
)

router = APIRouter(prefix="/chapters/{chapter_id}/pages", tags=["pages"])


@router.get("", response_model=list[PageInfo])
def list_pages(chapter_id: str) -> list[PageInfo]:
    """List all pages in a chapter with extraction status."""
    service = ChapterService()
    try:
        chapter = service.get_chapter(chapter_id)
        return chapter.pages
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{page_num}", response_model=PageDetail)
def get_page(chapter_id: str, page_num: int) -> PageDetail:
    """Get page details, image metadata, and extracted PageContext if available."""
    service = ChapterService()
    try:
        return service.get_page(chapter_id, page_num)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{page_num}", response_model=Chapter)
def delete_page(chapter_id: str, page_num: int, delete_file: bool = False) -> Chapter:
    """Delete a page from chapter and renumber remaining pages."""
    service = ChapterService()
    try:
        return service.delete_page(chapter_id, page_num, delete_image_file=delete_file)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{page_num}/image")
def get_page_image(chapter_id: str, page_num: int) -> FileResponse:
    """Stream raw image file for a given page."""
    service = ChapterService()
    try:
        page = service.get_page(chapter_id, page_num)
        img_path = Path(page.file_path)
        if not img_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found on disk")
        return FileResponse(img_path)
    except (ChapterNotFoundError, PageNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{page_num}", response_model=PageDetail)
def update_page_correction(chapter_id: str, page_num: int, payload: PageContext) -> PageDetail:
    """Save user corrections to a page's context without modifying raw model output."""
    service = ChapterService()
    try:
        return service.save_page_correction(chapter_id, page_num, payload)
    except (ChapterNotFoundError, PageNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


