"""
Character tracking, roster management, and cross-page ID resolution service.

Maintains stable character IDs across pages, aggregates known characters,
and supports renaming and merging character IDs across a chapter.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.schemas.character import KnownCharacter
from app.schemas.page_context import PageContext
from app.services.chapter_service import natural_sort_key

logger = logging.getLogger(__name__)


class CharacterServiceError(Exception):
    """Base exception for character service errors."""
    pass


class CharacterService:
    """Service to track and manage character rosters and cross-page consistency."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.results_dir = self.settings.RESULTS_DIR

    def _get_roster_file(self, chapter_id: str) -> Path:
        """Return the path to characters.json for the given chapter."""
        return self.results_dir / chapter_id / "characters.json"

    def get_known_characters(self, chapter_id: str) -> list[KnownCharacter]:
        """Aggregate known characters across all page results in a chapter."""
        chapter_res_dir = self.results_dir / chapter_id
        if not chapter_res_dir.is_dir():
            return []

        # 1. Check custom roster overrides if saved
        roster_file = self._get_roster_file(chapter_id)
        custom_roster: dict[str, dict[str, Any]] = {}
        if roster_file.is_file():
            try:
                roster_data = json.loads(roster_file.read_text(encoding="utf-8"))
                for entry in roster_data:
                    custom_roster[entry["id"]] = entry
            except Exception as exc:
                logger.warning(f"Failed to read custom roster file: {exc}")

        # 2. Aggregate from all page-*.json files (skipping *.raw.json)
        page_files = sorted(
            [f for f in chapter_res_dir.glob("page-*.json") if not f.name.endswith(".raw.json")],
            key=lambda p: natural_sort_key(p.name),
        )

        char_map: dict[str, dict[str, Any]] = {}

        for pf in page_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                page_num = data.get("page", 1)

                # Process character appearances
                for ch in data.get("characters", []):
                    cid = ch.get("id")
                    if not cid:
                        continue

                    if cid not in char_map:
                        char_map[cid] = {
                            "id": cid,
                            "name": custom_roster.get(cid, {}).get("name"),
                            "description": ch.get("description") or custom_roster.get(cid, {}).get("description"),
                            "first_seen_page": page_num,
                            "occurrences": 0,
                            "pages": [],
                        }

                    if page_num not in char_map[cid]["pages"]:
                        char_map[cid]["pages"].append(page_num)
                        char_map[cid]["occurrences"] += 1

                    # Keep best description
                    if ch.get("description") and not char_map[cid]["description"]:
                        char_map[cid]["description"] = ch["description"]

                # Also track any speaker/target IDs from text regions that might not be in characters list
                for tx in data.get("texts", []):
                    speaker = tx.get("speaker")
                    if speaker and speaker not in char_map:
                        char_map[speaker] = {
                            "id": speaker,
                            "name": custom_roster.get(speaker, {}).get("name"),
                            "description": custom_roster.get(speaker, {}).get("description"),
                            "first_seen_page": page_num,
                            "occurrences": 1,
                            "pages": [page_num],
                        }
                    elif speaker and page_num not in char_map[speaker]["pages"]:
                        char_map[speaker]["pages"].append(page_num)
                        char_map[speaker]["occurrences"] += 1

            except Exception as exc:
                logger.warning(f"Error reading page file {pf}: {exc}")

        # Also include any characters saved in custom roster that may not appear yet
        for cid, custom in custom_roster.items():
            if cid not in char_map:
                char_map[cid] = {
                    "id": cid,
                    "name": custom.get("name"),
                    "description": custom.get("description"),
                    "first_seen_page": custom.get("first_seen_page", 1),
                    "occurrences": custom.get("occurrences", 0),
                    "pages": custom.get("pages", []),
                }

        known_list = [KnownCharacter.model_validate(val) for val in char_map.values()]
        known_list.sort(key=lambda x: (x.first_seen_page, natural_sort_key(x.id)))
        return known_list

    def get_known_characters_dict(self, chapter_id: str) -> dict[str, str]:
        """Get mapping of {id: description} for prompt injection in extraction pipeline."""
        known = self.get_known_characters(chapter_id)
        result: dict[str, str] = {}
        for ch in known:
            desc = ch.name or ch.description or "character"
            result[ch.id] = desc
        return result

    def rename_character(
        self,
        chapter_id: str,
        old_id: str,
        new_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> list[KnownCharacter]:
        """Rename a character ID across all page JSON results in a chapter."""
        if not old_id or not new_id:
            raise ValueError("Both old_id and new_id must be provided")

        chapter_res_dir = self.results_dir / chapter_id
        if not chapter_res_dir.is_dir():
            return []

        page_files = sorted(
            [f for f in chapter_res_dir.glob("page-*.json") if not f.name.endswith(".raw.json")],
            key=lambda p: natural_sort_key(p.name),
        )

        for pf in page_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                modified = False

                # 1. Replace character ID
                for ch in data.get("characters", []):
                    if ch.get("id") == old_id:
                        ch["id"] = new_id
                        if description is not None:
                            ch["description"] = description
                        modified = True

                # 2. Replace speaker & target in texts
                for tx in data.get("texts", []):
                    if tx.get("speaker") == old_id:
                        tx["speaker"] = new_id
                        modified = True
                    if tx.get("target") == old_id:
                        tx["target"] = new_id
                        modified = True

                if modified:
                    # Validate and write back
                    validated = PageContext.model_validate(data)
                    pf.write_text(
                        json.dumps(validated.model_dump(), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
            except Exception as exc:
                logger.error(f"Failed to update page {pf} during rename: {exc}")

        # Update roster file
        roster_file = self._get_roster_file(chapter_id)
        known = self.get_known_characters(chapter_id)
        if name or description:
            for k in known:
                if k.id == new_id:
                    if name is not None:
                        k.name = name
                    if description is not None:
                        k.description = description

        roster_file.write_text(
            json.dumps([k.model_dump() for k in known], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return self.get_known_characters(chapter_id)

    def merge_characters(
        self,
        chapter_id: str,
        source_id: str,
        target_id: str,
        description: str | None = None,
    ) -> list[KnownCharacter]:
        """Merge source_id into target_id across all pages in a chapter."""
        if source_id == target_id:
            raise ValueError("source_id and target_id must be different")

        chapter_res_dir = self.results_dir / chapter_id
        if not chapter_res_dir.is_dir():
            return []

        page_files = sorted(
            [f for f in chapter_res_dir.glob("page-*.json") if not f.name.endswith(".raw.json")],
            key=lambda p: natural_sort_key(p.name),
        )

        for pf in page_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                modified = False

                # 1. Update character list & deduplicate
                updated_chars = []
                seen_ids = set()

                for ch in data.get("characters", []):
                    if ch.get("id") == source_id:
                        ch["id"] = target_id
                        if description is not None:
                            ch["description"] = description
                        modified = True

                    cid = ch.get("id")
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        updated_chars.append(ch)
                    else:
                        modified = True

                data["characters"] = updated_chars

                # 2. Update texts speaker & target
                for tx in data.get("texts", []):
                    if tx.get("speaker") == source_id:
                        tx["speaker"] = target_id
                        modified = True
                    if tx.get("target") == source_id:
                        tx["target"] = target_id
                        modified = True

                if modified:
                    validated = PageContext.model_validate(data)
                    pf.write_text(
                        json.dumps(validated.model_dump(), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
            except Exception as exc:
                logger.error(f"Failed to update page {pf} during merge: {exc}")

        # Remove source_id from existing roster file so it won't re-appear via custom_roster
        roster_file = self._get_roster_file(chapter_id)
        if roster_file.is_file():
            try:
                existing = json.loads(roster_file.read_text(encoding="utf-8"))
                cleaned = [e for e in existing if e.get("id") != source_id]
                roster_file.write_text(
                    json.dumps(cleaned, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning(f"Failed to clean roster file during merge: {exc}")

        # Re-aggregate and save updated roster
        known = self.get_known_characters(chapter_id)
        roster_file.write_text(
            json.dumps([k.model_dump() for k in known], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return known
