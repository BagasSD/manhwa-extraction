"""
Panel detection and cropping for the "Extract Image" pipeline.

Runs 100% locally (Pillow + NumPy, no model, no tokens) and is independent of
context extraction: it only needs the raw page images. See
docs/plan-fitur-panel-crop.md.

Flow: detect (auto_detected) -> human review via PUT (reviewed) -> crop-all
into data/extractedImage/{chapter_id}/.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.core.config import Settings, get_settings
from app.models.page import PageInfo
from app.schemas.page_context import Panel
from app.schemas.panel import (
    CropAllResult,
    DetectPanelsRequest,
    ExtractedImage,
    PagePanels,
    PanelDetectionStatus,
)
from app.services import panel_store
from app.services.chapter_service import ChapterService, PageNotFoundError
from app.services.image_service import ImageInput, ImageService

logger = logging.getLogger(__name__)

# A row/column is "blank" (gutter) when this share of its pixels is within
# _BLANK_TOLERANCE grey levels of its median: flat white, black or colour
# gutters pass, lines crossing art do not. Measured on real webtoon pages:
# gutters stay within 0-8 grey levels (WebP noise), while very dark art
# (values 0-26) must still count as content.
_BLANK_SHARE = 0.98
_BLANK_TOLERANCE = 8

# Text-only blocks (narration boxes, bubbles, captions floating in gutters) are
# not panels. They have few grey levels (low histogram entropy) but strong
# contrast; art has high entropy, and dark art that also has low entropy has
# low contrast. Measured: text <= 2.4 bits, std >= 46; art >= 2.9 bits.
_TEXT_MAX_ENTROPY = 2.6
_TEXT_MIN_STD = 30.0


@dataclass(frozen=True)
class DetectionParams:
    """Size thresholds, relative to page width so they scale with resolution."""

    min_gutter: float = 0.015  # blank run shorter than this is not a gutter
    min_height: float = 0.06  # smaller blocks (stray SFX strokes, dots) are dropped
    min_width: float = 0.15
    skip_text_only: bool = True  # drop narration boxes / bubbles between panels

    def pixels(self, width: int) -> tuple[int, int, int]:
        return (
            max(6, round(width * self.min_gutter)),
            max(16, round(width * self.min_height)),
            max(16, round(width * self.min_width)),
        )


def _blank_mask(gray: np.ndarray, axis: int) -> np.ndarray:
    """Per-row (axis=1) or per-column (axis=0) mask of near-uniform lines."""
    # The median of every 4th pixel is as good as the full one for a flat
    # gutter and is ~4x cheaper on 800x14000 strips.
    sample = gray[:, ::4] if axis == 1 else gray[::4, :]
    median = np.median(sample, axis=axis, keepdims=True)
    near = np.abs(gray - median) <= _BLANK_TOLERANCE
    return near.mean(axis=axis) >= _BLANK_SHARE


def is_text_only(gray_block: np.ndarray) -> bool:
    """True for a block that is lettering on a flat background rather than art."""
    hist = np.bincount((gray_block // 16).ravel(), minlength=16) / gray_block.size
    nonzero = hist[hist > 0]
    entropy = float(-(nonzero * np.log2(nonzero)).sum())
    return entropy < _TEXT_MAX_ENTROPY and float(gray_block.std()) >= _TEXT_MIN_STD


def _content_runs(blank: np.ndarray, min_gutter: int) -> list[tuple[int, int]]:
    """[start, end) runs of content, bridging blank gaps shorter than `min_gutter`."""
    runs: list[tuple[int, int]] = []
    content = np.flatnonzero(~blank)
    if content.size == 0:
        return runs
    start = prev = int(content[0])
    for idx in content[1:]:
        idx = int(idx)
        if idx - prev - 1 >= min_gutter:
            runs.append((start, prev + 1))
            start = idx
        prev = idx
    runs.append((start, prev + 1))
    return runs


def _split_block(
    gray: np.ndarray,
    top: int,
    left: int,
    min_gutter: int,
    depth: int,
) -> list[tuple[int, int, int, int]]:
    """Recursive XY-cut: split on horizontal gutters, then vertical ones, and trim margins.

    Returns (ymin, xmin, ymax, xmax) boxes in page coordinates.
    """
    rows = _content_runs(_blank_mask(gray, axis=1), min_gutter)
    boxes: list[tuple[int, int, int, int]] = []
    for y0, y1 in rows:
        band = gray[y0:y1]
        cols = _content_runs(_blank_mask(band, axis=0), min_gutter)
        for x0, x1 in cols:
            block = band[:, x0:x1]
            if depth > 0 and (len(rows) > 1 or len(cols) > 1):
                boxes.extend(_split_block(block, top + y0, left + x0, min_gutter, depth - 1))
                continue
            # Trim blank rows left inside this column range
            inner = _content_runs(_blank_mask(block, axis=1), min_gutter)
            if inner:
                boxes.append((top + y0 + inner[0][0], left + x0, top + y0 + inner[-1][1], left + x1))
    return boxes


def detect_panels(image: ImageInput, params: DetectionParams | None = None) -> list[Panel]:
    """Detect panels by gutter scanning (projection profile / XY-cut).

    Webtoon pages are long strips whose panels are separated by flat-colour
    gutters. Rows (then columns inside each band) that are near-uniform are
    treated as gutters; content between them becomes a panel. A page without
    gutters (full-bleed or splash art) yields a single panel.

    Tuned on real webtoon strips. Known limit: a panel whose only frame is a
    1-2 px line around a flat interior may be trimmed to its art, because such
    rows still read as 98% uniform. A stricter share was measured to merge
    neighbouring panels across noisy gutters, which is worse for webtoons.
    The review step exists to fix these cases.
    """
    params = params or DetectionParams()
    img = ImageService.load_image(image)
    gray = np.asarray(ImageOps.grayscale(img.convert("RGB")), dtype=np.int16)
    height, width = gray.shape
    min_gutter, min_height, min_width = params.pixels(width)

    boxes = _split_block(gray, 0, 0, min_gutter, depth=2)
    boxes = [b for b in boxes if b[2] - b[0] >= min_height and b[3] - b[1] >= min_width]
    if params.skip_text_only:
        boxes = [b for b in boxes if not is_text_only(gray[b[0]:b[2], b[1]:b[3]])]
    boxes.sort(key=lambda b: (b[0], b[1]))
    return [
        Panel(panel_index=i, bbox=[ymin, xmin, ymax, xmax])
        for i, (ymin, xmin, ymax, xmax) in enumerate(boxes, start=1)
    ]


def crop_region(image: Image.Image, bbox: list[int]) -> Image.Image:
    """Crop [ymin, xmin, ymax, xmax] out of `image`, clamped to its bounds."""
    ymin, xmin, ymax, xmax = bbox
    xmin, xmax = max(0, xmin), min(image.width, xmax)
    ymin, ymax = max(0, ymin), min(image.height, ymax)
    if xmax <= xmin or ymax <= ymin:
        raise ValueError(f"Panel bbox {bbox} lies outside the {image.width}x{image.height} image")
    return image.crop((xmin, ymin, xmax, ymax))


# ---------------------------------------------------------------------------
# Chapter-level pipeline: detect -> review -> crop-all
# ---------------------------------------------------------------------------

_CROP_NAME_RE = re.compile(r"^page(\d+)-chapter(.+)-crop(\d+)\.png$")


def crop_filename(page_num: int, chapter_id: str, crop_index: int) -> str:
    """`page{n}-chapter{id}-crop{i}.png`, zero-padded so files sort in reading order."""
    return f"page{page_num:03d}-chapter{chapter_id}-crop{crop_index:02d}.png"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PanelsNotFoundError(Exception):
    """Raised when a page has no panel data yet (detection not run)."""


class PanelsNotReviewedError(Exception):
    """Raised by crop-all while some pages still hold unreviewed boxes."""

    def __init__(self, unreviewed_pages: list[int]):
        super().__init__(f"{len(unreviewed_pages)} page(s) not reviewed yet: {unreviewed_pages}")
        self.unreviewed_pages = unreviewed_pages


class PanelService:
    """Detection jobs, human review and final cropping for one chapter at a time.

    Never touches context extraction (Ollama, page-{n}.json, chapter context).
    """

    # Detection jobs per chapter, shared across instances (like BatchService)
    _jobs: dict[str, PanelDetectionStatus] = {}
    _tasks: dict[str, asyncio.Task[Any]] = {}

    def __init__(self, settings: Settings | None = None, chapter_service: ChapterService | None = None):
        self.settings = settings or get_settings()
        self.chapter_service = chapter_service or ChapterService(settings=self.settings)
        self.results_dir = self.settings.RESULTS_DIR

    # --- single page -------------------------------------------------------

    def _page_info(self, chapter_id: str, page_num: int) -> PageInfo:
        for page in self.chapter_service.get_chapter(chapter_id).pages:
            if page.page_number == page_num:
                return page
        raise PageNotFoundError(f"Page {page_num} not found in chapter '{chapter_id}'")

    def detect_page(self, chapter_id: str, page: PageInfo) -> PagePanels:
        """Auto-detect one page and save it as `auto_detected`, replacing its boxes."""
        image = ImageService.load_image(page.file_path)
        page_panels = PagePanels(
            page=page.page_number,
            image_width=image.width,
            image_height=image.height,
            status="auto_detected",
            panels=detect_panels(image),
            updated_at=_now(),
        )
        panel_store.save_page_panels(self.results_dir, chapter_id, page_panels)
        return page_panels

    def get_page_panels(self, chapter_id: str, page_num: int) -> PagePanels:
        self._page_info(chapter_id, page_num)
        page_panels = panel_store.load_page_panels(self.results_dir, chapter_id, page_num)
        if page_panels is None:
            raise PanelsNotFoundError(f"Panels for page {page_num} have not been detected yet")
        return page_panels

    def save_reviewed_panels(self, chapter_id: str, page_num: int, boxes: list[list[int]]) -> PagePanels:
        """Store the human-adjusted boxes of a page and mark it `reviewed`.

        Boxes are clamped to the image and renumbered in reading order (top to
        bottom, then left to right). Earlier crops of the page stay valid only
        if the boxes did not change.
        """
        page = self._page_info(chapter_id, page_num)
        existing = panel_store.load_page_panels(self.results_dir, chapter_id, page_num)
        if existing is not None:
            width, height = existing.image_width, existing.image_height
        else:
            with Image.open(page.file_path) as img:
                width, height = img.size

        clamped: list[list[int]] = []
        for ymin, xmin, ymax, xmax in boxes:
            box = [max(0, ymin), max(0, xmin), min(height, ymax), min(width, xmax)]
            if box[2] - box[0] < 1 or box[3] - box[1] < 1:
                raise ValueError(f"Panel box {[ymin, xmin, ymax, xmax]} lies outside the {width}x{height} page")
            clamped.append(box)
        clamped.sort(key=lambda b: (b[0], b[1]))

        unchanged = existing is not None and [p.bbox for p in existing.panels] == clamped
        panels = [
            Panel(
                panel_index=i,
                bbox=box,
                status="reviewed",
                image_path=existing.panels[i - 1].image_path if unchanged and existing else None,
            )
            for i, box in enumerate(clamped, start=1)
        ]
        page_panels = PagePanels(
            page=page_num,
            image_width=width,
            image_height=height,
            status="reviewed",
            panels=panels,
            updated_at=_now(),
            cropped_at=existing.cropped_at if unchanged and existing else None,
        )
        panel_store.save_page_panels(self.results_dir, chapter_id, page_panels)
        return page_panels

    # --- detection job -----------------------------------------------------

    def get_detection_status(self, chapter_id: str) -> PanelDetectionStatus:
        self.chapter_service.get_chapter(chapter_id)
        return self._jobs.get(chapter_id) or PanelDetectionStatus(chapter_id=chapter_id)

    def start_detection(self, chapter_id: str, request: DetectPanelsRequest | None = None) -> PanelDetectionStatus:
        """Start auto-detection in the background; progress via get_detection_status."""
        request = request or DetectPanelsRequest()
        chapter = self.chapter_service.get_chapter(chapter_id)
        current = self._jobs.get(chapter_id)
        if current and current.status == "running":
            return current

        pages = [p for p in chapter.pages if request.pages is None or p.page_number in request.pages]
        job = PanelDetectionStatus(
            chapter_id=chapter_id,
            status="running",
            total_pages=len(pages),
            message=f"Detecting panels on {len(pages)} page(s)...",
        )
        self._jobs[chapter_id] = job
        self._tasks[chapter_id] = asyncio.create_task(self._run_detection(chapter_id, pages, request, job))
        return job

    async def wait_for_detection(self, chapter_id: str) -> PanelDetectionStatus:
        """Await a running detection job (used by tests and scripts)."""
        task = self._tasks.get(chapter_id)
        if task:
            await task
        return self.get_detection_status(chapter_id)

    async def _run_detection(
        self,
        chapter_id: str,
        pages: list[PageInfo],
        request: DetectPanelsRequest,
        job: PanelDetectionStatus,
    ) -> None:
        try:
            for page in pages:
                job.current_page = page.page_number
                existing = panel_store.load_page_panels(self.results_dir, chapter_id, page.page_number)
                if existing and existing.status == "reviewed" and not request.overwrite_reviewed:
                    job.skipped_pages += 1
                else:
                    try:
                        # CPU-bound: keep the event loop (and the API) responsive
                        await asyncio.to_thread(self.detect_page, chapter_id, page)
                        job.detected_pages += 1
                    except Exception as exc:
                        logger.error(f"Panel detection failed on page {page.page_number} of {chapter_id}: {exc}")
                        job.failed_pages += 1
                        job.error = f"Page {page.page_number}: {exc}"
                job.processed_pages += 1
                job.message = f"Detected {job.processed_pages}/{job.total_pages} page(s)"

            job.status = "completed"
            job.current_page = None
            job.message = (
                f"Panels detected on {job.detected_pages} page(s)"
                + (f", {job.skipped_pages} reviewed page(s) kept" if job.skipped_pages else "")
                + (f", {job.failed_pages} failed" if job.failed_pages else "")
            )
        except Exception as exc:
            logger.exception(f"Panel detection job for {chapter_id} crashed: {exc}")
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Panel detection failed: {exc}"

    # --- crop --------------------------------------------------------------

    def output_dir(self, chapter_id: str) -> Path:
        return self.settings.EXTRACTED_IMAGE_DIR / chapter_id

    def unreviewed_pages(self, chapter_id: str) -> list[int]:
        """Pages without detection or with boxes a human has not reviewed yet."""
        chapter = self.chapter_service.get_chapter(chapter_id)
        return [
            p.page_number
            for p in chapter.pages
            if panel_store.page_panel_status(
                panel_store.load_page_panels(self.results_dir, chapter_id, p.page_number)
            ) in ("none", "auto_detected")
        ]

    def crop_all_reviewed(self, chapter_id: str) -> CropAllResult:
        """Crop every reviewed panel of the chapter into data/extractedImage/{chapter_id}/.

        Refuses to run while any page is unreviewed, so no crop ever comes from
        a box a human has not validated. Previous crops of the chapter are
        replaced, so deleted boxes leave no stale files behind.
        """
        unreviewed = self.unreviewed_pages(chapter_id)
        if unreviewed:
            raise PanelsNotReviewedError(unreviewed)

        chapter = self.chapter_service.get_chapter(chapter_id)
        out_dir = self.output_dir(chapter_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.iterdir():
            if old.is_file() and _CROP_NAME_RE.match(old.name):
                old.unlink()

        files: list[str] = []
        pages_cropped = 0
        for page in chapter.pages:
            page_panels = panel_store.load_page_panels(self.results_dir, chapter_id, page.page_number)
            if page_panels is None:  # excluded by the guard above
                continue
            if page_panels.panels:
                image = ImageService.load_image(page.file_path)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() or image.mode == "P" else "RGB")
                if image.size != (page_panels.image_width, page_panels.image_height):
                    logger.warning(
                        f"Page {page.page_number} of {chapter_id} is now {image.size}, panels were drawn on "
                        f"{page_panels.image_width}x{page_panels.image_height}; cropping with clamped boxes"
                    )
                for panel in page_panels.panels:
                    name = crop_filename(page.page_number, chapter_id, panel.panel_index)
                    # Still lossless; level 1 encodes ~3x faster than the default for
                    # ~10% larger files (measured on 800px-wide webtoon crops)
                    crop_region(image, panel.bbox).save(out_dir / name, format="PNG", compress_level=1)
                    panel.image_path = str(out_dir / name)
                    files.append(name)
                pages_cropped += 1
            page_panels.cropped_at = _now()
            panel_store.save_page_panels(self.results_dir, chapter_id, page_panels)

        return CropAllResult(
            chapter_id=chapter_id,
            output_dir=str(out_dir.resolve()),
            total_crops=len(files),
            pages_cropped=pages_cropped,
            files=files,
        )

    def list_extracted_images(self, chapter_id: str) -> list[ExtractedImage]:
        self.chapter_service.get_chapter(chapter_id)
        out_dir = self.output_dir(chapter_id)
        if not out_dir.is_dir():
            return []
        images: list[ExtractedImage] = []
        for path in sorted(out_dir.iterdir()):
            match = _CROP_NAME_RE.match(path.name)
            if path.is_file() and match:
                images.append(
                    ExtractedImage(
                        filename=path.name,
                        page=int(match.group(1)),
                        crop_index=int(match.group(3)),
                        size_bytes=path.stat().st_size,
                    )
                )
        return images

    def extracted_image_path(self, chapter_id: str, filename: str) -> Path:
        """Resolve a crop file by name; only real crop names inside the chapter folder are served."""
        out_dir = self.output_dir(chapter_id)
        path = out_dir / filename
        if not _CROP_NAME_RE.match(filename) or path.parent != out_dir or not path.is_file():
            raise FileNotFoundError(f"Extracted image '{filename}' not found")
        return path
