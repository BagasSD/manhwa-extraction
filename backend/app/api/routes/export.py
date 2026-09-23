"""Export API routes for chapter data and context."""

from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
)
from app.services.export_service import ExportService, ExportServiceError

router = APIRouter(prefix="/chapters/{chapter_id}/export", tags=["export"])


@router.get("/json")
def export_chapter_json(
    chapter_id: str,
    download: bool = Query(False, description="Set to true to trigger file attachment download"),
) -> Response:
    """Export complete chapter structure, roster, synthesized context, and page results as JSON."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    export_service = ExportService()
    try:
        data = export_service.export_json(chapter_id, save_to_file=True)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{chapter_id}.json"'
        return Response(content=json_str, media_type="application/json", headers=headers)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JSON export failed: {exc}",
        ) from exc


@router.get("/txt", response_class=PlainTextResponse)
def export_chapter_txt(
    chapter_id: str,
    download: bool = Query(False, description="Set to true to trigger file attachment download"),
) -> PlainTextResponse:
    """Export downstream-AI-optimized TXT representation of chapter context and page extractions."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    export_service = ExportService()
    try:
        txt_content = export_service.export_txt(chapter_id, save_to_file=True)
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{chapter_id}.txt"'
        return PlainTextResponse(content=txt_content, headers=headers)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TXT export failed: {exc}",
        ) from exc
