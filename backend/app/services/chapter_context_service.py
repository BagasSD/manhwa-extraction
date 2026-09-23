"""
Chapter Context Generation Service.

Aggregates reviewed page records into structured chapter-level context
using Ollama (text-only prompt without resending images).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.schemas.chapter_context import (
    ChapterCharacterContext,
    ChapterContext,
    ChapterDialogue,
    ChapterEvent,
    ChapterTransition,
)
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    natural_sort_key,
)
from app.services.character_service import CharacterService
from app.services.ollama_service import OllamaError, OllamaService
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)


class ChapterContextError(Exception):
    """Base exception for chapter context generation errors."""
    pass


class ChapterContextNotFoundError(ChapterContextError, FileNotFoundError):
    """Raised when chapter context has not been generated yet."""
    pass


class ChapterContextService:
    """Service to aggregate page-level records and generate chapter-level context."""

    def __init__(
        self,
        settings: Settings | None = None,
        ollama_service: OllamaService | None = None,
        chapter_service: ChapterService | None = None,
        character_service: CharacterService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ollama_service = ollama_service or OllamaService(settings=self.settings)
        self.chapter_service = chapter_service or ChapterService(settings=self.settings)
        self.character_service = character_service or CharacterService(settings=self.settings)

    def _get_context_file(self, chapter_id: str) -> Path:
        return self.settings.RESULTS_DIR / chapter_id / "context.json"

    def _get_raw_context_file(self, chapter_id: str) -> Path:
        return self.settings.RESULTS_DIR / chapter_id / "context.raw.json"

    def _load_prompt(self) -> str:
        prompt_file = self.settings.PROMPTS_DIR / "chapter_context.txt"
        if prompt_file.is_file():
            return prompt_file.read_text(encoding="utf-8").strip()
        return (
            "You are a chapter context organizer for a manhwa/comic.\n\n"
            "Build structured chapter context from the provided page extraction results.\n\n"
            "Keep:\n"
            "- characters\n"
            "- important events\n"
            "- important dialogue\n"
            "- speaker and target\n"
            "- actions\n"
            "- locations\n"
            "- scene transitions\n"
            "- cause/effect when supported\n\n"
            "Rules:\n"
            "- Prefer human-corrected data when available.\n"
            "- Use only information from the provided page data.\n"
            "- Do not invent facts, dialogue, characters, motivations, or events.\n"
            "- Preserve uncertainty.\n"
            "- Do not translate dialogue.\n"
            "- Do not write the final YouTube script.\n"
            "- Remove repetitive visual details.\n"
            "- Keep chronological order.\n"
            "- Return JSON only."
        )

    def prepare_pages_payload(self, chapter_id: str) -> dict[str, Any]:
        """Collect and optimize page records for LLM context aggregation.

        Strips bounding boxes and visual token overhead per PRD §10.1.
        """
        chapter = self.chapter_service.get_chapter(chapter_id)
        chapter_res_dir = self.settings.RESULTS_DIR / chapter_id

        # Get known characters
        known_roster = self.character_service.get_known_characters(chapter_id)
        characters_payload = [
            {"id": c.id, "name": c.name, "description": c.description}
            for c in known_roster
        ]

        pages_payload: list[dict[str, Any]] = []
        excluded_types = set(self.settings.EXPORT_EXCLUDED_TEXT_TYPES)

        # Find all page result JSON files
        page_files = sorted(
            [
                f
                for f in chapter_res_dir.glob("page-*.json")
                if not f.name.endswith(".raw.json") and not f.name.endswith(".error.json")
            ],
            key=lambda p: natural_sort_key(p.name),
        )

        for pf in page_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                page_num = data.get("page", 1)

                # Strip bboxes from characters
                compact_chars = []
                for ch in data.get("characters", []):
                    item = {"id": ch.get("id")}
                    if ch.get("description"):
                        item["description"] = ch["description"]
                    if ch.get("expression"):
                        item["expression"] = ch["expression"]
                    if ch.get("emotion"):
                        item["emotion"] = ch["emotion"]
                    if ch.get("action"):
                        item["action"] = ch["action"]
                    compact_chars.append(item)

                # Strip bboxes from texts; skip excluded types (e.g. SFX)
                compact_texts = []
                for tx in data.get("texts", []):
                    if tx.get("type") in excluded_types:
                        continue
                    item = {"text": tx.get("text")}
                    if tx.get("id"):
                        item["id"] = tx["id"]
                    if tx.get("speaker"):
                        item["speaker"] = tx["speaker"]
                    if tx.get("target"):
                        item["target"] = tx["target"]
                    if tx.get("type") and tx["type"] not in ("unknown", "uk"):
                        item["type"] = tx["type"]
                    if tx.get("order"):
                        item["order"] = tx["order"]
                    compact_texts.append(item)

                scene = data.get("scene", {})
                compact_scene = {}
                if scene.get("location"):
                    compact_scene["location"] = scene["location"]
                if scene.get("situation"):
                    compact_scene["situation"] = scene["situation"]
                if scene.get("mood"):
                    compact_scene["mood"] = scene["mood"]
                if scene.get("actions"):
                    compact_scene["actions"] = scene["actions"]

                page_item: dict[str, Any] = {
                    "page": page_num,
                    "characters": compact_chars,
                    "texts": compact_texts,
                    "scene": compact_scene,
                }
                if data.get("visual_summary"):
                    page_item["visual_summary"] = data["visual_summary"]

                pages_payload.append(page_item)
            except Exception as exc:
                logger.warning(f"Failed to read page {pf} during context preparation: {exc}")

        return {
            "chapter_id": chapter_id,
            "title": chapter.title,
            "total_pages": chapter.total_pages,
            "roster": characters_payload,
            "pages": pages_payload,
        }

    def _normalize_context_dict(self, raw_data: dict[str, Any], chapter_id: str, title: str) -> dict[str, Any]:
        """Ensure standard keys are present in dictionary before Pydantic parsing."""
        data = dict(raw_data)
        data.setdefault("chapter_id", chapter_id)
        data.setdefault("title", title)
        data.setdefault("summary", data.get("overview") or data.get("description"))

        # Normalize characters
        chars = data.get("characters", [])
        norm_chars = []
        for ch in chars:
            if isinstance(ch, dict):
                norm_chars.append({
                    "id": ch.get("id") or ch.get("character_id", "c1"),
                    "name": ch.get("name"),
                    "description": ch.get("description"),
                    "role": ch.get("role"),
                    "actions": ch.get("actions", []),
                })
        data["characters"] = norm_chars

        # Normalize events
        events = data.get("events", [])
        norm_events = []
        for ev in events:
            if isinstance(ev, dict):
                pages = ev.get("pages", [])
                if isinstance(pages, int):
                    pages = [pages]
                norm_events.append({
                    "pages": pages,
                    "event": ev.get("event") or ev.get("description", ""),
                    "characters_involved": ev.get("characters_involved") or ev.get("characters", []),
                })
        data["events"] = norm_events

        # Normalize transitions
        transitions = data.get("transitions", [])
        norm_transitions = []
        for tr in transitions:
            if isinstance(tr, dict):
                pages = tr.get("pages", [])
                if isinstance(pages, int):
                    pages = [pages]
                norm_transitions.append({
                    "pages": pages,
                    "description": tr.get("description") or tr.get("transition", ""),
                    "from_location": tr.get("from_location") or tr.get("from"),
                    "to_location": tr.get("to_location") or tr.get("to"),
                })
        data["transitions"] = norm_transitions

        # Normalize dialogue
        dialogues = data.get("important_dialogue", []) or data.get("dialogue", [])
        norm_dialogues = []
        for dl in dialogues:
            if isinstance(dl, dict):
                norm_dialogues.append({
                    "page": dl.get("page", 1),
                    "speaker": dl.get("speaker"),
                    "target": dl.get("target"),
                    "text": dl.get("text", ""),
                })
        data["important_dialogue"] = norm_dialogues

        return data

    async def generate_chapter_context(
        self,
        chapter_id: str,
        force: bool = False,
    ) -> ChapterContext:
        """Aggregate reviewed page records and synthesize chapter-level context via Gemma."""
        context_file = self._get_context_file(chapter_id)
        if context_file.is_file() and not force:
            return self.get_chapter_context(chapter_id)

        chapter = self.chapter_service.get_chapter(chapter_id)
        system_prompt = self._load_prompt()
        payload = self.prepare_pages_payload(chapter_id)

        user_prompt = (
            f"Synthesize the chapter context for '{chapter.title}' (ID: {chapter_id}) "
            f"based on the following {len(payload['pages'])} page records:\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            raw_response = await self.ollama_service.generate(
                prompt=user_prompt,
                system=system_prompt,
                format="json",
            )
            raw_text = raw_response.get("response", "")
            raw_data = ValidationService.extract_json(raw_text)
        except Exception as exc:
            logger.error(f"Failed to generate chapter context with Ollama: {exc}")
            raise ChapterContextError(f"Ollama generation failed: {exc}") from exc

        norm_data = self._normalize_context_dict(raw_data, chapter_id, chapter.title)
        chapter_context = ChapterContext.model_validate(norm_data)

        # Persist raw and normalized context
        context_file.parent.mkdir(parents=True, exist_ok=True)
        raw_file = self._get_raw_context_file(chapter_id)
        raw_file.write_text(
            json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        context_file.write_text(
            json.dumps(chapter_context.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return chapter_context

    def get_chapter_context(self, chapter_id: str) -> ChapterContext:
        """Retrieve persisted chapter context."""
        context_file = self._get_context_file(chapter_id)
        if not context_file.is_file():
            raise ChapterContextNotFoundError(
                f"Chapter context for '{chapter_id}' has not been generated yet."
            )

        try:
            data = json.loads(context_file.read_text(encoding="utf-8"))
            return ChapterContext.model_validate(data)
        except Exception as exc:
            logger.error(f"Failed to load chapter context from {context_file}: {exc}")
            raise ChapterContextError(f"Failed to parse chapter context: {exc}") from exc

    def save_chapter_context(
        self,
        chapter_id: str,
        context: ChapterContext,
    ) -> ChapterContext:
        """Save manual user edits/corrections to chapter context."""
        context_file = self._get_context_file(chapter_id)
        context_file.parent.mkdir(parents=True, exist_ok=True)

        context_data = context.model_dump()
        context_data["chapter_id"] = chapter_id

        context_file.write_text(
            json.dumps(context_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return context
