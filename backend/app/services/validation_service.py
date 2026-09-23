"""
Validation and parsing service for LLM responses.

Extracts JSON from markdown or raw LLM output, normalizes short keys,
validates against Pydantic schemas, and detects suspicious extractions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.character import Character
from app.schemas.page_context import PageContext
from app.schemas.scene import Scene
from app.schemas.text_region import TextRegion


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
    pass


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

    @classmethod
    def normalize_dict(cls, data: dict[str, Any], page_num: int = 1) -> dict[str, Any]:
        """Normalize short internal LLM keys to canonical schema fields."""
        visual_summary = data.get("visual_summary") or data.get("summary") or data.get("vs")

        normalized: dict[str, Any] = {
            "page": data.get("page") or data.get("p") or page_num,
            "characters": [],
            "texts": [],
            "scene": {},
            "visual_summary": visual_summary if isinstance(visual_summary, str) and visual_summary.strip() else None,
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
                    "bbox": ch.get("bbox") or ch.get("b"),
                    "expression": ch.get("expression") or ch.get("e") or ch.get("expr"),
                    "emotion": ch.get("emotion") or ch.get("m"),
                    "action": ch.get("action") or ch.get("a"),
                }
                normalized["characters"].append(char_dict)

        # Texts normalization (t or texts)
        raw_texts = data.get("texts") or data.get("t") or []
        if isinstance(raw_texts, list):
            for i, tx in enumerate(raw_texts, start=1):
                if not isinstance(tx, dict):
                    continue
                tid = tx.get("id") or tx.get("tid") or f"t{i}"
                conf = tx.get("confidence") if tx.get("confidence") is not None else tx.get("conf")
                text_dict = {
                    "id": str(tid),
                    "text": tx.get("text") or tx.get("x") or "",
                    "speaker": tx.get("speaker") or tx.get("y"),
                    "target": tx.get("target") or tx.get("z"),
                    "type": tx.get("type") or tx.get("k") or "speech",
                    "bbox": tx.get("bbox") or tx.get("b"),
                    "order": tx.get("order") or tx.get("o") or i,
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

        return issues

    @classmethod
    def validate_page_context(
        cls,
        raw_input: str | dict[str, Any],
        page_num: int = 1,
        known_character_ids: set[str] | None = None,
        check_suspicious: bool = False,
    ) -> PageContext:
        """Parse raw text or dict, normalize keys, and validate as PageContext."""
        if isinstance(raw_input, str):
            extracted = cls.extract_json(raw_input)
        elif isinstance(raw_input, dict):
            extracted = raw_input
        else:
            raise SchemaValidationError(f"Expected string or dict, got {type(raw_input)}")

        normalized = cls.normalize_dict(extracted, page_num=page_num)

        try:
            ctx = PageContext.model_validate(normalized)
        except ValidationError as exc:
            raise SchemaValidationError(
                f"Page context schema validation failed: {exc}",
                raw_json=extracted,
                errors=exc.errors(),
            ) from exc

        if check_suspicious:
            issues = cls.detect_suspicious(ctx, known_character_ids=known_character_ids)
            if issues:
                raise SuspiciousExtractionError(
                    f"Suspicious extraction anomalies detected: {'; '.join(issues)}",
                    raw_json=extracted,
                )

        return ctx
