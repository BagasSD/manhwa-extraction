"""
Export Service for Manhwa Context Extractor.

Generates structured JSON and downstream-AI-optimized TXT exports
containing chapter metadata, character rosters, synthesized chapter context,
and page-by-page extractions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.services.chapter_context_service import (
    ChapterContextNotFoundError,
    ChapterContextService,
)
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    natural_sort_key,
)
from app.services.character_service import CharacterService

logger = logging.getLogger(__name__)


class ExportServiceError(Exception):
    """Base exception for export errors."""
    pass


class ExportService:
    """Service to export chapter data in JSON and AI-optimized TXT formats."""

    def __init__(
        self,
        settings: Settings | None = None,
        chapter_service: ChapterService | None = None,
        character_service: CharacterService | None = None,
        chapter_context_service: ChapterContextService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.exports_dir = self.settings.EXPORTS_DIR
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.chapter_service = chapter_service or ChapterService(settings=self.settings)
        self.character_service = character_service or CharacterService(settings=self.settings)
        self.chapter_context_service = (
            chapter_context_service or ChapterContextService(settings=self.settings)
        )

    def export_json(self, chapter_id: str, save_to_file: bool = True) -> dict[str, Any]:
        """Generate complete structured JSON export of chapter and all pages."""
        chapter = self.chapter_service.get_chapter(chapter_id)
        known_characters = self.character_service.get_known_characters(chapter_id)

        # Retrieve chapter context if available
        chapter_context = None
        try:
            ctx = self.chapter_context_service.get_chapter_context(chapter_id)
            chapter_context = ctx.model_dump()
        except (ChapterContextNotFoundError, Exception):
            chapter_context = None

        # Gather all pages with extracted context
        pages_data: list[dict[str, Any]] = []
        for p in chapter.pages:
            detail = self.chapter_service.get_page(chapter_id, p.page_number)
            page_dict: dict[str, Any] = {
                "page_number": detail.page_number,
                "filename": detail.filename,
                "status": detail.status,
                "context": detail.context.model_dump() if detail.context else None,
            }
            if detail.error_message:
                page_dict["error"] = detail.error_message
            pages_data.append(page_dict)

        payload: dict[str, Any] = {
            "chapter_id": chapter.id,
            "title": chapter.title,
            "source_path": chapter.source_path,
            "total_pages": chapter.total_pages,
            "completed_pages": chapter.completed_pages,
            "failed_pages": chapter.failed_pages,
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
            "characters_roster": [c.model_dump() for c in known_characters],
            "chapter_context": chapter_context,
            "pages": pages_data,
        }

        if save_to_file:
            export_file = self.exports_dir / f"{chapter_id}.json"
            export_file.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        return payload

    def export_txt(self, chapter_id: str, save_to_file: bool = True) -> str:
        """Generate downstream-AI-optimized TXT export per PRD §11."""
        chapter = self.chapter_service.get_chapter(chapter_id)
        known_characters = self.character_service.get_known_characters(chapter_id)

        # Retrieve chapter context if available
        chapter_context = None
        try:
            chapter_context = self.chapter_context_service.get_chapter_context(chapter_id)
        except (ChapterContextNotFoundError, Exception):
            chapter_context = None

        lines: list[str] = []

        # Header
        lines.append(f"CHAPTER: {chapter.title} (ID: {chapter.id})")
        lines.append(f"TOTAL PAGES: {chapter.total_pages}")
        if chapter_context and chapter_context.summary:
            lines.append(f"SUMMARY: {chapter_context.summary}")
        lines.append("")

        # Chapter-level Synthesis (if available)
        if chapter_context:
            if chapter_context.events:
                lines.append("MAJOR EVENTS:")
                for ev in chapter_context.events:
                    page_str = (
                        f"[Pages {ev.pages[0]}-{ev.pages[-1]}]"
                        if len(ev.pages) > 1
                        else f"[Page {ev.pages[0]}]"
                        if ev.pages
                        else "[Chapter]"
                    )
                    involved = (
                        f" (Characters: {', '.join(ev.characters_involved)})"
                        if ev.characters_involved
                        else ""
                    )
                    lines.append(f"- {page_str} {ev.event}{involved}")
                lines.append("")

            if chapter_context.transitions:
                lines.append("SCENE TRANSITIONS:")
                for tr in chapter_context.transitions:
                    page_str = (
                        f"[Pages {tr.pages[0]}-{tr.pages[-1]}]"
                        if len(tr.pages) > 1
                        else f"[Page {tr.pages[0]}]"
                        if tr.pages
                        else "[Scene]"
                    )
                    lines.append(f"- {page_str} {tr.description}")
                lines.append("")

        # Character Roster
        if chapter_context and chapter_context.characters:
            lines.append("CHARACTER ROSTER:")
            for ch in chapter_context.characters:
                name_str = f" ({ch.name})" if ch.name else ""
                desc_str = f": {ch.description}" if ch.description else ""
                role_str = f" [Role: {ch.role}]" if ch.role else ""
                actions_str = f" (Actions: {', '.join(ch.actions)})" if ch.actions else ""
                lines.append(f"- {ch.id}{name_str}{desc_str}{role_str}{actions_str}")
            lines.append("")
        elif known_characters:
            lines.append("CHARACTER ROSTER:")
            for ch in known_characters:
                name_str = f" ({ch.name})" if ch.name else ""
                desc_str = f": {ch.description}" if ch.description else ""
                first_seen = f" [first seen: p.{ch.first_seen_page}, total appearances: {ch.occurrences}]"
                lines.append(f"- {ch.id}{name_str}{desc_str}{first_seen}")
            lines.append("")

        # Page-by-page breakdown
        lines.append("=" * 40)
        lines.append("PAGE-BY-PAGE CONTEXT BREAKDOWN")
        lines.append("=" * 40)
        lines.append("")

        for p in chapter.pages:
            detail = self.chapter_service.get_page(chapter_id, p.page_number)
            lines.append(f"PAGE {p.page_number}")
            lines.append("")

            if not detail.context:
                if detail.status in ("failed", "manual_review"):
                    lines.append(f"STATUS: Manual review needed ({detail.error_message or 'extraction incomplete'})")
                else:
                    lines.append("STATUS: Pending extraction")
                lines.append("")
                continue

            ctx = detail.context

            if ctx.visual_summary:
                lines.append(f"VISUAL SUMMARY: {ctx.visual_summary}")
                lines.append("")

            # Scene
            lines.append("SCENE")
            scene = ctx.scene
            lines.append(f"Location: {scene.location or 'Unknown'}")
            lines.append(f"Situation: {scene.situation or 'Unknown'}")
            if scene.mood:
                lines.append(f"Mood: {scene.mood}")
            if scene.actions:
                lines.append(f"Actions: {'; '.join(scene.actions)}")
            lines.append("")

            # Characters visible
            lines.append("CHARACTERS")
            if ctx.characters:
                for c in ctx.characters:
                    details = []
                    if c.description:
                        details.append(c.description)
                    if c.expression:
                        details.append(f"expression: {c.expression}")
                    if c.emotion:
                        details.append(f"emotion: {c.emotion}")
                    if c.action:
                        details.append(f"action: {c.action}")
                    desc = f": {', '.join(details)}" if details else ""
                    lines.append(f"{c.id}{desc}")
            else:
                lines.append("- (None visible)")
            lines.append("")

            # Dialogue / Text
            lines.append("TEXT")
            if ctx.texts:
                sorted_texts = sorted(ctx.texts, key=lambda t: t.order)
                for tx in sorted_texts:
                    speaker = tx.speaker or "Unknown"
                    target_str = f" → {tx.target}" if tx.target else ""
                    type_str = f" [{tx.type}]" if tx.type and tx.type not in ("speech", "sp") else ""
                    lines.append(f"[{tx.order}] {speaker}{target_str}{type_str}")
                    lines.append(f'"{tx.text}"')
                    lines.append("")
            else:
                lines.append("- (None)")
                lines.append("")

        content = "\n".join(lines).strip() + "\n"

        if save_to_file:
            export_file = self.exports_dir / f"{chapter_id}.txt"
            export_file.write_text(content, encoding="utf-8")

        return content
