"""
Validation and parsing service for LLM responses.

Extracts JSON from markdown or raw LLM output, normalizes short keys,
validates against Pydantic schemas, and detects suspicious extractions.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from pydantic import ValidationError

from app.schemas.character import Character
from app.schemas.page_context import PageContext
from app.schemas.scene import Scene
from app.schemas.text_region import TextRegion
from app.services.image_service import ImageSegment

# Keys models use for the text list when they don't follow the prompt's "texts"
# (e.g. the prompt says "visible text" and the model answers "visible_text").
# Without these aliases the transcription is silently dropped and texts == [].
TEXT_LIST_KEYS = (
    "texts", "t", "text", "text_regions", "visible_text", "visible_texts",
    "dialogue", "dialogues", "dialog", "ocr", "ocr_text", "ocr_texts",
    "transcription", "transcriptions",
)
TEXT_CONTENT_KEYS = ("text", "x", "content", "transcription", "value", "dialogue", "line")
TEXT_TYPE_KEYS = ("type", "k", "text_type", "kind", "category")

KNOWN_TOP_LEVEL_KEYS = {
    *TEXT_LIST_KEYS, "page", "p", "characters", "c", "scene", "s",
    "visual_summary", "summary", "vs", "has_text", "ocr_confidence",
}

# Placeholder strings models put in speaker/target instead of null.
_NULL_REFS = {"", "null", "none", "unknown", "n/a", "?"}

# Words in a visual summary that imply the page has lettering. If they appear
# while texts is empty, the model saw text but didn't transcribe it.
_TEXT_INDICATOR_RE = re.compile(
    r"\b(text|texts|caption|captions|narration|narrative|narrator|dialogue|dialog|"
    r"speech bubbles?|thought bubbles?|bubbles?|sfx|sound effects?|onomatopoeia|"
    r"written|writing|lettering|says|said|saying)\b",
    re.IGNORECASE,
)

# Prefix of issues meaning "the page likely has text the model did not
# transcribe". The extraction retry escalates these to crop + upscale ("tiled").
MISSING_TEXT_ISSUE_PREFIX = "Missing text:"


class SchemaValidationError(Exception):
    """Raised when JSON schema validation fails against Pydantic models."""

    def __init__(self, message: str, raw_json: Any = None, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.raw_json = raw_json
        self.errors = errors or []


class JSONExtractionError(SchemaValidationError):
    """Raised when JSON cannot be parsed or found in model output."""
    pass


class SuspiciousExtractionError(SchemaValidationError):
    """Raised when extraction contains suspicious anomalies warranting a retry."""

    def __init__(self, message: str, raw_json: Any = None, issues: list[str] | None = None):
        super().__init__(message, raw_json=raw_json)
        self.issues = issues or []

    @property
    def is_missing_text(self) -> bool:
        """True when the anomaly suggests text was visible but not transcribed."""
        return any(issue.startswith(MISSING_TEXT_ISSUE_PREFIX) for issue in self.issues)


class ValidationService:
    """Service to parse, normalize, and validate LLM outputs into PageContext."""

    @classmethod
    def extract_json(cls, raw_text: str) -> dict[str, Any]:
        """Extract a JSON object from raw LLM output string.

        Supports markdown code fences, embedded JSON objects, and raw JSON strings.
        """
        if not raw_text or not raw_text.strip():
            raise JSONExtractionError("LLM response text is empty")

        cleaned = raw_text.strip()

        # 1. Try markdown code fences ```json ... ``` or ``` ... ```
        json_fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if json_fence_match:
            candidate = json_fence_match.group(1).strip()
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        # 2. Try parsing full cleaned text
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # 3. Find outermost curly braces { ... }
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = cleaned[start_idx : end_idx + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError as exc:
                raise JSONExtractionError(
                    f"Failed to parse extracted JSON block: {exc}",
                    raw_json=candidate,
                ) from exc

        raise JSONExtractionError(
            "No valid JSON object found in response",
            raw_json=raw_text,
        )

    @staticmethod
    def _first(item: dict[str, Any], keys: Sequence[str]) -> Any:
        """Return the first truthy value among `keys` in `item`."""
        for key in keys:
            value = item.get(key)
            if value:
                return value
        return None

    @staticmethod
    def _char_ref(value: Any) -> str | None:
        """Normalize a speaker/target reference, mapping placeholder strings to None."""
        if value is None:
            return None
        ref = str(value).strip()
        return None if ref.lower() in _NULL_REFS else ref

    @staticmethod
    def _map_bbox(
        item: dict[str, Any],
        bbox: Any,
        segments: Sequence[ImageSegment] | None,
    ) -> Any:
        """Convert a segment-relative bbox to page coordinates when the page was tiled.

        Malformed boxes are returned untouched so schema validation still rejects
        them. A box whose segment cannot be identified is dropped rather than
        placed at a guessed position.
        """
        if not segments or bbox is None:
            return bbox
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return bbox
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox):
            return bbox

        seg = item.get("seg", item.get("segment"))
        if seg is None and len(segments) == 1:
            seg = 1
        try:
            seg_index = int(seg) - 1
        except (TypeError, ValueError):
            return None
        if not 0 <= seg_index < len(segments):
            return None
        return segments[seg_index].to_page_bbox(bbox)

    @classmethod
    def _find_text_list(cls, data: dict[str, Any]) -> list[Any]:
        """Locate the model's text list under any known alias key."""
        for key in TEXT_LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list) and value:
                return value
            # A bare string (all text concatenated) becomes one region per line.
            if key != "t" and isinstance(value, str) and value.strip():
                return [line.strip() for line in value.splitlines() if line.strip()]
        return []

    @classmethod
    def normalize_dict(
        cls,
        data: dict[str, Any],
        page_num: int = 1,
        segments: Sequence[ImageSegment] | None = None,
    ) -> dict[str, Any]:
        """Normalize short internal LLM keys to canonical schema fields.

        `segments` is the tile layout when the page was sent in "tiled" mode;
        bboxes are then mapped from segment-relative to page-level coordinates.
        """
        visual_summary = data.get("visual_summary") or data.get("summary") or data.get("vs")

        normalized: dict[str, Any] = {
            "page": data.get("page") or data.get("p") or page_num,
            "characters": [],
            "texts": [],
            "scene": {},
            "visual_summary": visual_summary if isinstance(visual_summary, str) and visual_summary.strip() else None,
            "has_text": data.get("has_text"),
            "ocr_confidence": data.get("ocr_confidence"),
        }

        # Characters normalization (c or characters)
        raw_chars = data.get("characters") or data.get("c") or []
        if isinstance(raw_chars, list):
            for i, ch in enumerate(raw_chars, start=1):
                if not isinstance(ch, dict):
                    continue
                cid = ch.get("id") or ch.get("cid") or f"c{i}"
                char_dict = {
                    "id": str(cid),
                    "description": ch.get("description") or ch.get("d") or ch.get("desc"),
                    "bbox": cls._map_bbox(ch, ch.get("bbox") or ch.get("b"), segments),
                    "expression": ch.get("expression") or ch.get("e") or ch.get("expr"),
                    "emotion": ch.get("emotion") or ch.get("m"),
                    "action": ch.get("action") or ch.get("a"),
                }
                normalized["characters"].append(char_dict)

        # Texts normalization (texts, t, or an alias such as visible_text/dialogue)
        for i, tx in enumerate(cls._find_text_list(data), start=1):
            if isinstance(tx, str):
                tx = {"text": tx, "type": "unknown"}
            if not isinstance(tx, dict):
                continue
            tid = tx.get("id") or tx.get("tid") or f"t{i}"
            conf = tx.get("confidence") if tx.get("confidence") is not None else tx.get("conf")
            text_dict = {
                "id": str(tid),
                "text": cls._first(tx, TEXT_CONTENT_KEYS) or "",
                "speaker": cls._char_ref(tx.get("speaker") or tx.get("y") or tx.get("speaker_id")),
                "target": cls._char_ref(tx.get("target") or tx.get("z") or tx.get("target_id")),
                "type": cls._first(tx, TEXT_TYPE_KEYS) or "speech",
                "bbox": cls._map_bbox(tx, tx.get("bbox") or tx.get("b"), segments),
                "order": tx.get("order") or tx.get("o") or tx.get("reading_order") or i,
                "confidence": conf,
            }
            normalized["texts"].append(text_dict)

        # Scene normalization (s or scene)
        raw_scene = data.get("scene") or data.get("s") or {}
        if isinstance(raw_scene, dict):
            actions = raw_scene.get("actions") or raw_scene.get("a") or []
            if isinstance(actions, str):
                actions = [actions]
            elif not isinstance(actions, (list, tuple)):
                actions = []

            normalized["scene"] = {
                "location": raw_scene.get("location") or raw_scene.get("l") or raw_scene.get("loc"),
                "situation": raw_scene.get("situation") or raw_scene.get("q") or raw_scene.get("sit"),
                "actions": actions,
                "mood": raw_scene.get("mood") or raw_scene.get("m"),
            }

        return normalized

    @classmethod
    def detect_suspicious(
        cls,
        page_context: PageContext,
        known_character_ids: set[str] | None = None,
    ) -> list[str]:
        """Detect suspicious extractions (e.g. duplicate IDs, nonexistent character refs, invalid confidence)."""
        issues: list[str] = []

        # 1. Duplicate text IDs
        text_ids = [tx.id for tx in page_context.texts if tx.id]
        if len(text_ids) != len(set(text_ids)):
            issues.append(f"Duplicate text IDs detected: {text_ids}")

        # 2. Duplicate character IDs
        char_ids = {c.id for c in page_context.characters if c.id}
        if len(char_ids) != len(page_context.characters):
            issues.append("Duplicate character IDs detected")

        # 3. Nonexistent speaker or target character references
        all_valid_char_ids = set(char_ids)
        if known_character_ids:
            all_valid_char_ids.update(known_character_ids)

        if all_valid_char_ids:
            for tx in page_context.texts:
                if tx.speaker and tx.speaker not in all_valid_char_ids:
                    issues.append(
                        f"Text '{tx.id}' references nonexistent speaker '{tx.speaker}'"
                    )
                if tx.target and tx.target not in all_valid_char_ids:
                    issues.append(
                        f"Text '{tx.id}' references nonexistent target '{tx.target}'"
                    )

        # 4. Invalid confidence or bounding boxes
        for tx in page_context.texts:
            if tx.confidence is not None and not (0.0 <= tx.confidence <= 1.0):
                issues.append(f"Text '{tx.id}' has invalid confidence: {tx.confidence}")
            if tx.bbox is not None:
                if len(tx.bbox) != 4:
                    issues.append(f"Text '{tx.id}' has invalid bbox length: {len(tx.bbox)}")

        for c in page_context.characters:
            if c.bbox is not None:
                if len(c.bbox) != 4:
                    issues.append(f"Character '{c.id}' has invalid bbox length: {len(c.bbox)}")

        # 5. Text the model saw but did not transcribe (plan v2 §6)
        issues.extend(cls.detect_missing_text(page_context))

        return issues

    @classmethod
    def detect_missing_text(cls, page_context: PageContext) -> list[str]:
        """Flag pages whose own description implies text that is absent from `texts`.

        An empty `texts` is only trusted when nothing else in the answer hints at
        lettering; otherwise "empty because unreadable" would pass silently as
        "empty because there is no text".
        """
        prefix = MISSING_TEXT_ISSUE_PREFIX
        issues: list[str] = []

        for tx in page_context.texts:
            if not tx.text.strip():
                issues.append(f"{prefix} text '{tx.id}' has no transcribed content")

        if page_context.ocr_confidence == "low":
            issues.append(f"{prefix} model reported low OCR confidence")

        if page_context.texts:
            return issues

        if page_context.has_text:
            issues.append(f"{prefix} model reported visible text (has_text=true) but texts is empty")
        described = " ".join(
            part for part in (page_context.visual_summary, page_context.scene.situation) if part
        )
        match = _TEXT_INDICATOR_RE.search(described)
        if match:
            issues.append(
                f"{prefix} description mentions '{match.group(0)}' but texts is empty"
            )
        return issues

    @staticmethod
    def find_unrecognized_keys(data: dict[str, Any]) -> list[str]:
        """Top-level keys with content that normalization does not read (possible lost text)."""
        return sorted(
            key for key, value in data.items()
            if key not in KNOWN_TOP_LEVEL_KEYS and isinstance(value, (list, dict, str)) and value
        )

    @classmethod
    def validate_page_context(
        cls,
        raw_input: str | dict[str, Any],
        page_num: int = 1,
        known_character_ids: set[str] | None = None,
        check_suspicious: bool = False,
        flag_suspicious: bool = False,
        segments: Sequence[ImageSegment] | None = None,
    ) -> PageContext:
        """Parse raw text or dict, normalize keys, and validate as PageContext.

        check_suspicious: raise SuspiciousExtractionError on anomalies (triggers a retry).
        flag_suspicious: record anomalies in `review_flags` instead of raising, so a
            last-attempt result is kept but marked for manual review.
        segments: tile layout when the page was sent in "tiled" mode.
        """
        if isinstance(raw_input, str):
            extracted = cls.extract_json(raw_input)
        elif isinstance(raw_input, dict):
            extracted = raw_input
        else:
            raise SchemaValidationError(f"Expected string or dict, got {type(raw_input)}")

        normalized = cls.normalize_dict(extracted, page_num=page_num, segments=segments)

        try:
            ctx = PageContext.model_validate(normalized)
        except ValidationError as exc:
            raise SchemaValidationError(
                f"Page context schema validation failed: {exc}",
                raw_json=extracted,
                errors=exc.errors(),
            ) from exc

        if check_suspicious or flag_suspicious:
            issues = cls.detect_suspicious(ctx, known_character_ids=known_character_ids)
            unrecognized = cls.find_unrecognized_keys(extracted)
            if unrecognized and not ctx.texts:
                issues.append(
                    f"{MISSING_TEXT_ISSUE_PREFIX} texts is empty but the output has "
                    f"unrecognized keys {unrecognized}"
                )
            if issues and check_suspicious:
                raise SuspiciousExtractionError(
                    f"Suspicious extraction anomalies detected: {'; '.join(issues)}",
                    raw_json=extracted,
                    issues=issues,
                )
            ctx.review_flags = issues

        return ctx
