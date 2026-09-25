"""
Filesystem persistence for panel data (the "Extract Image" pipeline).

Panel files live in their own sub-folder, `data/results/{chapter_id}/panels/
page-{n}.panels.json`, not next to `page-{n}.json`: the context-extraction
services glob `page-*.json` in the chapter folder and must never pick panel
data up as page context. Kept free of other service imports so both
chapter_service and panel_service can use it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.panel import PagePanels

logger = logging.getLogger(__name__)

PANELS_DIRNAME = "panels"


def panels_dir(results_dir: Path, chapter_id: str) -> Path:
    return results_dir / chapter_id / PANELS_DIRNAME


def panels_path(results_dir: Path, chapter_id: str, page_num: int) -> Path:
    return panels_dir(results_dir, chapter_id) / f"page-{page_num:03d}.panels.json"


def load_page_panels(results_dir: Path, chapter_id: str, page_num: int) -> PagePanels | None:
    """Read a page's panels, or None if the page was never detected (or the file is unreadable)."""
    path = panels_path(results_dir, chapter_id, page_num)
    if not path.is_file():
        return None
    try:
        return PagePanels.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Ignoring unreadable panel file {path}: {exc}")
        return None


def save_page_panels(results_dir: Path, chapter_id: str, page_panels: PagePanels) -> Path:
    path = panels_path(results_dir, chapter_id, page_panels.page)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page_panels.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def page_panel_status(page_panels: PagePanels | None) -> str:
    """"none" | "auto_detected" | "reviewed" | "cropped" for one page."""
    if page_panels is None:
        return "none"
    if page_panels.status != "reviewed" or any(p.status != "reviewed" for p in page_panels.panels):
        return "auto_detected"
    if page_panels.cropped_at and all(
        p.image_path and Path(p.image_path).is_file() for p in page_panels.panels
    ):
        return "cropped"
    return "reviewed"
