"""Chapter API routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.models.chapter import Chapter, ChapterCreate, ChapterDownloadRequest, ChapterSummary
from app.schemas.chapter_context import ChapterContext
from app.schemas.character import (
    CharacterMergeRequest,
    CharacterRenameRequest,
    KnownCharacter,
)
from app.services.chapter_context_service import (
    ChapterContextNotFoundError,
    ChapterContextService,
)
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    InvalidSourceDirectoryError,
)
from app.services.character_service import CharacterService
from app.services.download_service import DownloadError, DownloadService

router = APIRouter(prefix="/chapters", tags=["chapters"])


@router.post("", response_model=Chapter, status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterCreate) -> Chapter:
    """Create a new chapter by discovering pages in a source directory."""
    service = ChapterService()
    try:
        return service.create_chapter(payload)
    except InvalidSourceDirectoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/download", response_model=Chapter, status_code=status.HTTP_201_CREATED)
async def download_chapter(payload: ChapterDownloadRequest) -> Chapter:
    """Download chapter images from a URL and register as a chapter."""
    service = DownloadService()
    try:
        return await service.download_chapter_from_url(
            url=payload.url,
            title=payload.title,
            chapter_id=payload.id,
            custom_headers=payload.custom_headers,
        )
    except DownloadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download chapter: {exc}",
        ) from exc



@router.get("", response_model=list[ChapterSummary])
def list_chapters() -> list[ChapterSummary]:
    """List all registered chapters."""
    service = ChapterService()
    return service.list_chapters()


@router.get("/{chapter_id}", response_model=Chapter)
def get_chapter(chapter_id: str) -> Chapter:
    """Get chapter details and ordered page list."""
    service = ChapterService()
    try:
        return service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: str) -> None:
    """Delete chapter metadata."""
    service = ChapterService()
    deleted = service.delete_chapter(chapter_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chapter '{chapter_id}' not found")


@router.get("/{chapter_id}/characters", response_model=list[KnownCharacter])
def get_known_characters(chapter_id: str) -> list[KnownCharacter]:
    """Get aggregated character tracking list across chapter pages."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    char_service = CharacterService()
    return char_service.get_known_characters(chapter_id)


@router.post("/{chapter_id}/characters/rename", response_model=list[KnownCharacter])
def rename_character(chapter_id: str, payload: CharacterRenameRequest) -> list[KnownCharacter]:
    """Rename a character ID across all pages in the chapter."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    char_service = CharacterService()
    try:
        return char_service.rename_character(
            chapter_id=chapter_id,
            old_id=payload.old_id,
            new_id=payload.new_id,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{chapter_id}/characters/merge", response_model=list[KnownCharacter])
def merge_characters(chapter_id: str, payload: CharacterMergeRequest) -> list[KnownCharacter]:
    """Merge source character ID into target character ID across all chapter pages."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    char_service = CharacterService()
    try:
        return char_service.merge_characters(
            chapter_id=chapter_id,
            source_id=payload.source_id,
            target_id=payload.target_id,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{chapter_id}/context", response_model=ChapterContext)
async def generate_chapter_context(
    chapter_id: str,
    force: bool = Query(False, description="Force re-generation even if context exists"),
) -> ChapterContext:
    """Generate or retrieve aggregated chapter-level context using Gemma."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    context_service = ChapterContextService()
    try:
        return await context_service.generate_chapter_context(chapter_id=chapter_id, force=force)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate chapter context: {exc}",
        ) from exc


@router.get("/{chapter_id}/context", response_model=ChapterContext)
def get_chapter_context(chapter_id: str) -> ChapterContext:
    """Retrieve persisted chapter-level context."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    context_service = ChapterContextService()
    try:
        return context_service.get_chapter_context(chapter_id)
    except ChapterContextNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load chapter context: {exc}",
        ) from exc


@router.put("/{chapter_id}/context", response_model=ChapterContext)
def update_chapter_context(chapter_id: str, payload: ChapterContext) -> ChapterContext:
    """Save user edits to chapter context."""
    chapter_service = ChapterService()
    try:
        chapter_service.get_chapter(chapter_id)
    except ChapterNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    context_service = ChapterContextService()
    return context_service.save_chapter_context(chapter_id, payload)
