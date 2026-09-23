"""
Chapter and Page management service.

Handles chapter discovery, natural numerical page ordering,
chapter metadata persistence, page status tracking, error persistence, and result retrieval.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.models.chapter import Chapter, ChapterCreate, ChapterSummary
from app.models.page import PageDetail, PageInfo
from app.schemas.page_context import PageContext

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ChapterServiceError(Exception):
    """Base exception for chapter management errors."""
    pass


class ChapterNotFoundError(ChapterServiceError, FileNotFoundError):
    """Raised when a chapter is not found."""
    pass


class PageNotFoundError(ChapterServiceError, FileNotFoundError):
    """Raised when a requested page is not found in the chapter."""
    pass


class InvalidSourceDirectoryError(ChapterServiceError, ValueError):
    """Raised when the specified source directory is invalid or empty."""
    pass


def natural_sort_key(s: str) -> list[int | str]:
    """Turn a string into a list of string and number chunks for natural sorting."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


class ChapterService:
    """Service managing chapter discovery, persistence, and page statuses."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.chapters_dir = self.settings.CHAPTERS_DIR
        self.results_dir = self.settings.RESULTS_DIR

        # Ensure base directories exist
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def slugify(text: str) -> str:
        """Create a filesystem-safe ID from title or folder name."""
        slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
        return re.sub(r"[-\s]+", "-", slug) or "chapter"

    def discover_pages(self, source_path: Path | str) -> list[Path]:
        """Discover and naturally sort all image files in a directory."""
        dir_path = Path(source_path)
        if not dir_path.is_dir():
            raise InvalidSourceDirectoryError(f"Directory not found: {dir_path}")

        image_files = [
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ]

        if not image_files:
            raise InvalidSourceDirectoryError(f"No supported image files found in: {dir_path}")

        image_files.sort(key=lambda p: natural_sort_key(p.name))
        return image_files

    def _get_page_status(self, chapter_id: str, page_num: int) -> tuple[str, bool, bool, str | None]:
        """Check if raw, normalized, or error result files exist for a page.

        Returns (status, has_raw_result, has_normalized_result, error_message).
        """
        prefix = f"page-{page_num:03d}"
        chapter_res_dir = self.results_dir / chapter_id

        raw_file = chapter_res_dir / f"{prefix}.raw.json"
        norm_file = chapter_res_dir / f"{prefix}.json"
        error_file = chapter_res_dir / f"{prefix}.error.json"

        has_raw = raw_file.is_file()
        has_norm = norm_file.is_file()
        error_msg: str | None = None

        if has_norm:
            status = "done"
            # Suspicious extraction kept after all retries: done, but needs review
            flags = self._read_review_flags(norm_file)
            if flags:
                status = "manual_review"
                error_msg = f"Needs review: {flags[0]}"
                if len(flags) > 1:
                    error_msg += f" (+{len(flags) - 1} more)"
        elif error_file.is_file():
            status = "manual_review"
            try:
                err_data = json.loads(error_file.read_text(encoding="utf-8"))
                error_msg = err_data.get("error", "Extraction failed; manual review required")
            except Exception:
                error_msg = "Extraction failed; manual review required"
        else:
            status = "pending"

        return status, has_raw, has_norm, error_msg

    @staticmethod
    def _read_review_flags(norm_file: Path) -> list[str]:
        """Return the review flags stored in a normalized page result, if any."""
        try:
            flags = json.loads(norm_file.read_text(encoding="utf-8")).get("review_flags")
        except Exception:
            return []
        return [str(f) for f in flags] if isinstance(flags, list) else []

    def create_chapter(self, payload: ChapterCreate) -> Chapter:
        """Create a chapter by discovering image pages from a source directory."""
        source_dir = Path(payload.source_path).resolve()
        image_files = self.discover_pages(source_dir)

        chapter_id = payload.id or self.slugify(payload.title or source_dir.name)

        # Build pages list
        pages: list[PageInfo] = []
        for idx, img_path in enumerate(image_files, start=1):
            status, has_raw, has_norm, error_msg = self._get_page_status(chapter_id, idx)
            pages.append(
                PageInfo(
                    page_number=idx,
                    filename=img_path.name,
                    file_path=str(img_path),
                    status=status,
                    has_raw_result=has_raw,
                    has_normalized_result=has_norm,
                    error_message=error_msg,
                )
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        chapter = Chapter(
            id=chapter_id,
            title=payload.title,
            source_path=str(source_dir),
            total_pages=len(pages),
            completed_pages=sum(1 for p in pages if p.has_normalized_result),
            failed_pages=sum(1 for p in pages if p.status in ("failed", "manual_review")),
            created_at=now_iso,
            updated_at=now_iso,
            pages=pages,
        )

        # Persist chapter metadata
        chapter_file = self.chapters_dir / f"{chapter_id}.json"
        chapter_file.write_text(
            json.dumps(chapter.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return chapter

    def list_chapters(self) -> list[ChapterSummary]:
        """List all registered chapters."""
        summaries: list[ChapterSummary] = []
        for file in self.chapters_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                chapter_id = data.get("id", file.stem)

                # Refresh progress counts
                pages_data = data.get("pages", [])
                total = len(pages_data)
                completed = 0
                failed = 0
                for p in pages_data:
                    p_num = p.get("page_number", 1)
                    st, _, has_norm, _ = self._get_page_status(chapter_id, p_num)
                    if has_norm:
                        completed += 1
                    elif st in ("failed", "manual_review"):
                        failed += 1

                summaries.append(
                    ChapterSummary(
                        id=chapter_id,
                        title=data.get("title", file.stem),
                        source_path=data.get("source_path", ""),
                        total_pages=total,
                        completed_pages=completed,
                        failed_pages=failed,
                        created_at=data.get("created_at", ""),
                        updated_at=data.get("updated_at", ""),
                    )
                )
            except Exception as exc:
                logger.error(f"Failed to read chapter file {file}: {exc}")
                continue

        summaries.sort(key=lambda c: natural_sort_key(c.id))
        return summaries

    def get_chapter(self, chapter_id: str) -> Chapter:
        """Get full chapter details with updated page statuses."""
        chapter_file = self.chapters_dir / f"{chapter_id}.json"
        if not chapter_file.is_file():
            raise ChapterNotFoundError(f"Chapter '{chapter_id}' not found")

        try:
            data = json.loads(chapter_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ChapterServiceError(f"Failed to parse chapter file: {exc}") from exc

        # Refresh page statuses dynamically
        pages: list[PageInfo] = []
        completed = 0
        failed = 0
        for p in data.get("pages", []):
            p_num = p["page_number"]
            status, has_raw, has_norm, error_msg = self._get_page_status(chapter_id, p_num)
            if has_norm:
                completed += 1
            elif status in ("failed", "manual_review") or p.get("status") in ("failed", "manual_review"):
                status = "manual_review"
                failed += 1

            pages.append(
                PageInfo(
                    page_number=p_num,
                    filename=p["filename"],
                    file_path=p["file_path"],
                    status=status,
                    has_raw_result=has_raw,
                    has_normalized_result=has_norm,
                    error_message=error_msg,
                )
            )

        return Chapter(
            id=chapter_id,
            title=data.get("title", chapter_id),
            source_path=data.get("source_path", ""),
            total_pages=len(pages),
            completed_pages=completed,
            failed_pages=failed,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            pages=pages,
        )

    def get_page(self, chapter_id: str, page_num: int) -> PageDetail:
        """Get page info and extracted context if present."""
        chapter = self.get_chapter(chapter_id)
        target_page: PageInfo | None = None
        for p in chapter.pages:
            if p.page_number == page_num:
                target_page = p
                break

        if not target_page:
            raise PageNotFoundError(f"Page {page_num} not found in chapter '{chapter_id}'")

        prefix = f"page-{page_num:03d}"
        chapter_res_dir = self.results_dir / chapter_id

        raw_file = chapter_res_dir / f"{prefix}.raw.json"
        norm_file = chapter_res_dir / f"{prefix}.json"

        raw_result: dict[str, Any] | None = None
        context: PageContext | None = None

        if raw_file.is_file():
            try:
                raw_result = json.loads(raw_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Failed to read raw result for page {page_num}: {exc}")

        if norm_file.is_file():
            try:
                norm_dict = json.loads(norm_file.read_text(encoding="utf-8"))
                context = PageContext.model_validate(norm_dict)
            except Exception as exc:
                logger.warning(f"Failed to validate normalized context for page {page_num}: {exc}")

        return PageDetail(
            page_number=target_page.page_number,
            filename=target_page.filename,
            file_path=target_page.file_path,
            status=target_page.status,
            has_raw_result=target_page.has_raw_result,
            has_normalized_result=target_page.has_normalized_result,
            error_message=target_page.error_message,
            raw_result=raw_result,
            context=context,
        )

    def delete_chapter(self, chapter_id: str) -> bool:
        """Delete chapter metadata file."""
        chapter_file = self.chapters_dir / f"{chapter_id}.json"
        if chapter_file.is_file():
            chapter_file.unlink()
            return True
        return False

    def save_page_error(
        self,
        chapter_id: str,
        page_num: int,
        error_message: str,
        attempts: int = 1,
    ) -> None:
        """Persist extraction error for a page to mark it for manual review."""
        chapter_res_dir = self.results_dir / chapter_id
        chapter_res_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"page-{page_num:03d}"
        error_file = chapter_res_dir / f"{prefix}.error.json"
        payload = {
            "page": page_num,
            "status": "manual_review",
            "error": error_message,
            "attempts": attempts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        error_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear_page_error(self, chapter_id: str, page_num: int) -> None:
        """Remove error record for a page if it exists."""
        prefix = f"page-{page_num:03d}"
        error_file = self.results_dir / chapter_id / f"{prefix}.error.json"
        if error_file.is_file():
            try:
                error_file.unlink()
            except OSError as exc:
                logger.warning(f"Failed to remove error file {error_file}: {exc}")

    def save_page_correction(
        self,
        chapter_id: str,
        page_num: int,
        page_context: PageContext,
    ) -> PageDetail:
        """Save user corrections for a page without overwriting raw AI output."""
        # Ensure chapter and page exist
        self.get_page(chapter_id, page_num)

        chapter_res_dir = self.results_dir / chapter_id
        chapter_res_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"page-{page_num:03d}"
        norm_file = chapter_res_dir / f"{prefix}.json"

        # Clear previous error state on successful manual correction
        self.clear_page_error(chapter_id, page_num)

        # Persist normalized & user-corrected context. A human save is the manual
        # review, so it resolves any suspicious-extraction flags.
        context_data = page_context.model_dump()
        context_data["page"] = page_num
        context_data["review_flags"] = []
        norm_file.write_text(
            json.dumps(context_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return self.get_page(chapter_id, page_num)

    def delete_page(self, chapter_id: str, page_num: int, delete_image_file: bool = False) -> Chapter:
        """Delete a single page from chapter and renumber remaining pages.

        Args:
            chapter_id: ID of the chapter.
            page_num: 1-indexed page number to delete.
            delete_image_file: If True, also unlink image file from disk.

        Returns:
            Updated Chapter model with remaining pages.
        """
        chapter_file = self.chapters_dir / f"{chapter_id}.json"
        if not chapter_file.is_file():
            raise ChapterNotFoundError(f"Chapter '{chapter_id}' not found")

        try:
            data = json.loads(chapter_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ChapterServiceError(f"Failed to parse chapter file: {exc}") from exc

        pages = data.get("pages", [])
        target_page_entry = None
        target_idx = -1
        for idx, p in enumerate(pages):
            if p.get("page_number") == page_num:
                target_page_entry = p
                target_idx = idx
                break

        if target_page_entry is None:
            raise PageNotFoundError(f"Page {page_num} not found in chapter '{chapter_id}'")

        chapter_res_dir = self.results_dir / chapter_id

        # 1. Remove result files for deleted page
        del_prefix = f"page-{page_num:03d}"
        for ext in (".json", ".raw.json", ".error.json"):
            f = chapter_res_dir / f"{del_prefix}{ext}"
            if f.is_file():
                try:
                    f.unlink()
                except OSError as exc:
                    logger.warning(f"Failed to remove {f}: {exc}")

        # 2. Optionally delete physical image file
        if delete_image_file:
            img_path = Path(target_page_entry.get("file_path", ""))
            if img_path.is_file():
                try:
                    img_path.unlink()
                except OSError as exc:
                    logger.warning(f"Failed to unlink image {img_path}: {exc}")

        # 3. Shift result files for subsequent pages
        # Renumber in ascending order
        for p in pages[target_idx + 1:]:
            old_num = p["page_number"]
            new_num = old_num - 1

            old_prefix = f"page-{old_num:03d}"
            new_prefix = f"page-{new_num:03d}"

            # Rename normalized context and update internal page field
            norm_old = chapter_res_dir / f"{old_prefix}.json"
            norm_new = chapter_res_dir / f"{new_prefix}.json"
            if norm_old.is_file():
                try:
                    pdata = json.loads(norm_old.read_text(encoding="utf-8"))
                    pdata["page"] = new_num
                    norm_new.write_text(json.dumps(pdata, indent=2, ensure_ascii=False), encoding="utf-8")
                    norm_old.unlink()
                except Exception as exc:
                    logger.warning(f"Failed to rename {norm_old} -> {norm_new}: {exc}")

            # Rename raw file
            raw_old = chapter_res_dir / f"{old_prefix}.raw.json"
            raw_new = chapter_res_dir / f"{new_prefix}.raw.json"
            if raw_old.is_file():
                try:
                    raw_old.rename(raw_new)
                except OSError as exc:
                    logger.warning(f"Failed to rename {raw_old} -> {raw_new}: {exc}")

            # Rename error file
            err_old = chapter_res_dir / f"{old_prefix}.error.json"
            err_new = chapter_res_dir / f"{new_prefix}.error.json"
            if err_old.is_file():
                try:
                    err_old.rename(err_new)
                except OSError as exc:
                    logger.warning(f"Failed to rename {err_old} -> {err_new}: {exc}")

            # Update page number in page metadata
            p["page_number"] = new_num

        # 4. Remove deleted page from chapter pages list
        pages.pop(target_idx)
        data["pages"] = pages
        data["total_pages"] = len(pages)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save updated chapter file
        chapter_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return self.get_chapter(chapter_id)

