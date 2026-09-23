"""
Single-page extraction pipeline service.

Orchestrates: image preprocessing -> Ollama model call -> JSON parsing & validation
-> raw and normalized result persistence.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.constants import OCR_CONFIDENCE_LEVELS
from app.schemas.page_context import PageContext
from app.services.image_service import ImageInput, ImageSegment, ImageService
from app.services.ollama_service import (
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaService,
)
from app.services.validation_service import (
    JSONExtractionError,
    SchemaValidationError,
    SuspiciousExtractionError,
    ValidationService,
)

logger = logging.getLogger(__name__)

TILED_MODE = "tiled"

# Canonical text types offered to the model (aliases are only accepted on input).
_OUTPUT_TEXT_TYPES = ["speech", "thought", "narration", "caption", "system", "sfx", "sign", "unknown"]
_NULLABLE_STRING: dict[str, Any] = {"type": ["string", "null"]}
_BBOX: dict[str, Any] = {"type": ["array", "null"], "items": {"type": "number"}}


def build_page_output_schema(segmented: bool = False) -> dict[str, Any]:
    """JSON schema of the page answer, sent as Ollama `format` (structured outputs).

    Pinning key names is what keeps the transcription in `texts`: with plain
    "json" mode the model may answer under its own keys (e.g. "visible_text").
    `has_text` comes first so the model commits to whether text exists before
    it writes the text list. `segmented` adds the "seg" tile index used by
    "tiled" preprocessing.
    """
    character: dict[str, Any] = {
        "id": {"type": "string"},
        "description": _NULLABLE_STRING,
        "expression": _NULLABLE_STRING,
        "emotion": _NULLABLE_STRING,
        "action": _NULLABLE_STRING,
        "bbox": _BBOX,
    }
    text: dict[str, Any] = {
        "id": {"type": "string"},
        "text": {"type": "string"},
        "type": {"type": "string", "enum": _OUTPUT_TEXT_TYPES},
        "speaker": _NULLABLE_STRING,
        "target": _NULLABLE_STRING,
        "order": {"type": "integer"},
        "confidence": {"type": ["number", "null"]},
        "bbox": _BBOX,
    }
    if segmented:
        character["seg"] = {"type": "integer"}
        text["seg"] = {"type": "integer"}

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties, "required": list(properties)}

    return obj({
        "has_text": {"type": "boolean"},
        "characters": {"type": "array", "items": obj(character)},
        "texts": {"type": "array", "items": obj(text)},
        "scene": obj({
            "location": _NULLABLE_STRING,
            "situation": _NULLABLE_STRING,
            "actions": {"type": "array", "items": {"type": "string"}},
            "mood": _NULLABLE_STRING,
        }),
        "visual_summary": _NULLABLE_STRING,
        "ocr_confidence": {"enum": [*OCR_CONFIDENCE_LEVELS, None]},
    })


class PageExtractionResult(BaseModel):
    """Result of a single-page extraction operation."""

    page_context: PageContext
    raw_response: dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    processing_time_ms: float = 0.0
    attempts: int = 1
    raw_path: str | None = None
    result_path: str | None = None
    preprocess_mode: str = "original"
    image_sizes: list[tuple[int, int]] = Field(
        default_factory=list, description="Size of each image sent on the final attempt"
    )


class ExtractionService:
    """Service to extract structured page context from a manhwa image."""

    def __init__(
        self,
        settings: Settings | None = None,
        ollama_service: OllamaService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ollama_service = ollama_service or OllamaService(settings=self.settings)
        # Set once the host rejects a JSON-schema `format`, so later pages skip it
        self._schema_rejected = False

    def _load_prompt(self, filename: str, fallback: str) -> str:
        """Load a prompt template from prompts directory, or return fallback."""
        prompt_path = self.settings.PROMPTS_DIR / filename
        if prompt_path.is_file():
            return prompt_path.read_text(encoding="utf-8").strip()
        return fallback.strip()

    def get_system_prompt(self) -> str:
        """Get the page extraction system prompt."""
        fallback = (
            "You are a visual context extractor for manhwa/comic pages.\n\n"
            "Analyze the provided page image and extract only information visually supported by the image.\n\n"
            "You have two separate jobs:\n"
            "1. TRANSCRIBE: copy every visible text (bubbles, narration/caption boxes, system windows, "
            "SFX, signs) into \"texts\", exactly as written, word for word.\n"
            "2. DESCRIBE: put what is shown only in \"characters\", \"scene\" and \"visual_summary\".\n\n"
            "If any text is visible, \"texts\" must not be empty.\n\n"
            "Return JSON with keys: has_text, characters (id, description, expression, emotion, action, bbox), "
            "texts (id, text, type, speaker, target, order, confidence, bbox), "
            "scene (location, situation, actions, mood), visual_summary, ocr_confidence (high|medium|low|null).\n"
            "Text type: speech | thought | narration | caption | system | sfx | sign | unknown.\n"
            "bbox: [ymin, xmin, ymax, xmax] normalized to 0-1000, or null.\n\n"
            "Rules:\n"
            "- Preserve visible text accurately.\n"
            "- Do not translate text.\n"
            "- Do not rewrite or summarize dialogue.\n"
            "- Do not invent text, names, events, or motivations.\n"
            "- Reuse known character IDs when provided.\n"
            "- Create new character IDs only when necessary.\n"
            "- Use null when information is unknown.\n"
            "- Use ? when an interpretation is uncertain.\n"
            "- Do not infer emotion solely from actions or appearance.\n"
            "- Do not provide a story summary.\n"
            "- Do not explain reasoning.\n"
            "- Return JSON only."
        )
        return self._load_prompt("page_extraction.txt", fallback)

    def get_retry_prompt(self) -> str:
        """Get the retry prompt template."""
        fallback = (
            "Re-check the provided manhwa page and return valid JSON.\n\n"
            "Focus on:\n"
            "- missing or incorrect text\n"
            "- OCR accuracy\n"
            "- text type\n"
            "- speaker\n"
            "- target\n"
            "- reading order\n"
            "- character consistency\n"
            "- expression\n"
            "- emotion\n"
            "- action\n"
            "- scene information\n\n"
            "Rules:\n"
            "- Use only visually supported information.\n"
            "- Do not invent unreadable text.\n"
            "- Do not invent names or events.\n"
            "- Do not translate text.\n"
            "- Use null when unknown.\n"
            "- Preserve uncertainty.\n"
            "- Do not explain reasoning.\n"
            "- Return JSON only."
        )
        # Check both page_retry.txt and page_reply.txt
        retry_path = self.settings.PROMPTS_DIR / "page_retry.txt"
        reply_path = self.settings.PROMPTS_DIR / "page_reply.txt"
        if retry_path.is_file():
            return retry_path.read_text(encoding="utf-8").strip()
        if reply_path.is_file():
            return reply_path.read_text(encoding="utf-8").strip()
        return fallback.strip()

    def build_user_prompt(
        self,
        known_characters: dict[str, str] | None = None,
        segment_count: int | None = None,
    ) -> str:
        """Build the user prompt with optional known characters list and tile layout."""
        prompt = "Analyze this page."
        if segment_count:
            prompt += (
                f"\n\nThe page is split into {segment_count} segment image(s), given in "
                "top-to-bottom order. Treat them as one page: list each character and each "
                "text once. Add \"seg\" (1 = first image) to every character and text, and "
                "give its bbox relative to that segment image."
            )
        if known_characters:
            prompt += "\n\nKnown characters:\n"
            for cid, desc in known_characters.items():
                prompt += f"{cid} = {desc}\n"
        return prompt.strip()

    @staticmethod
    def build_retry_hint(error: Exception | None) -> str:
        """Tell the model what was wrong with its previous answer."""
        if isinstance(error, SuspiciousExtractionError):
            if error.is_missing_text:
                return (
                    "Your previous answer missed text: the page appears to contain visible "
                    "text but \"texts\" was empty or incomplete. Look again at every bubble, "
                    "box, SFX and sign and transcribe each one word for word."
                )
            if error.issues:
                return "Fix these problems from your previous answer:\n- " + "\n- ".join(error.issues[:3])
        if isinstance(error, (SchemaValidationError, json.JSONDecodeError)):
            return "Your previous answer was not valid JSON with the required structure."
        return ""

    @staticmethod
    def select_preprocess_mode(attempt: int, base_mode: str, last_error: Exception | None) -> str:
        """Preprocessing for an attempt (PRD §13.1, plan v2 §4).

        Attempts 1-2 use the requested mode. Attempt 3+ switches strategy: to
        crop + upscale ("tiled") when the model missed text, otherwise to an
        alternative enhancement.
        """
        if attempt < 3:
            return base_mode
        if base_mode == TILED_MODE or (
            isinstance(last_error, SuspiciousExtractionError) and last_error.is_missing_text
        ):
            return TILED_MODE
        return "enhanced" if base_mode == "original" else "contrast"

    def prepare_images(
        self, image_input: ImageInput, mode: str
    ) -> tuple[list[Image.Image], list[ImageSegment] | None]:
        """Return the image(s) to send and, in tiled mode, their page layout."""
        if mode == TILED_MODE:
            segments = ImageService.split_into_segments(
                image_input,
                max_segments=self.settings.EXTRACTION_TILE_MAX_SEGMENTS,
                min_width=self.settings.EXTRACTION_TILE_MIN_WIDTH,
            )
            return [s.image for s in segments], segments
        return [ImageService.preprocess(image_input, mode=mode)], None

    async def _generate(
        self,
        prompt: str,
        images: list[Image.Image],
        system: str,
        segmented: bool,
    ) -> dict[str, Any]:
        """Call Ollama with the page schema, falling back to plain JSON mode if rejected."""
        options = {
            "temperature": min(self.settings.OLLAMA_TEMPERATURE, self.settings.EXTRACTION_MAX_TEMPERATURE)
        }
        use_schema = self.settings.EXTRACTION_STRUCTURED_OUTPUT and not self._schema_rejected
        output_format: str | dict[str, Any] = build_page_output_schema(segmented) if use_schema else "json"
        try:
            return await self.ollama_service.generate(
                prompt=prompt, images=images, system=system, format=output_format, options=options
            )
        except OllamaResponseError as exc:
            if (
                isinstance(output_format, str)
                or isinstance(exc, OllamaModelNotFoundError)
                or exc.status_code != 400
            ):
                raise
            logger.warning(f"Ollama rejected the JSON schema format; using plain JSON mode from now on: {exc}")
            self._schema_rejected = True
            return await self.ollama_service.generate(
                prompt=prompt, images=images, system=system, format="json", options=options
            )

    def save_results(
        self,
        page_context: PageContext,
        raw_response: dict[str, Any],
        chapter_id: str,
        page_num: int,
    ) -> tuple[Path, Path]:
        """Save raw and normalized results to data/results/{chapter_id}/."""
        chapter_result_dir = self.settings.RESULTS_DIR / chapter_id
        chapter_result_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"page-{page_num:03d}"
        raw_path = chapter_result_dir / f"{prefix}.raw.json"
        result_path = chapter_result_dir / f"{prefix}.json"

        # Save raw model response
        raw_path.write_text(json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8")

        # Save normalized PageContext
        result_path.write_text(
            json.dumps(page_context.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Clear any prior error file for this page
        error_path = chapter_result_dir / f"{prefix}.error.json"
        if error_path.is_file():
            try:
                error_path.unlink()
            except OSError:
                pass

        return raw_path, result_path

    async def extract_page(
        self,
        image_input: ImageInput,
        page_num: int = 1,
        known_characters: dict[str, str] | None = None,
        chapter_id: str | None = None,
        preprocess_mode: str = "original",
        max_retries: int = 1,
    ) -> PageExtractionResult:
        """Execute full single-page extraction pipeline.

        Follows PRD §13.1 Retry Policy:
        - attempt 1: normal extraction
        - attempt 2: retry prompt + what was wrong with the previous answer
        - attempt 3: alternative preprocessing ('tiled' crop + upscale when text
          was missed, otherwise 'enhanced') + retry prompt

        Suspicious anomalies trigger retries; if they survive the last attempt
        the result is kept but its `review_flags` mark it for manual review.

        Args:
            image_input: Image file path, bytes, or PIL Image.
            page_num: Page number index.
            known_characters: Known character dictionary {id: description}.
            chapter_id: Optional chapter ID to automatically persist results.
            preprocess_mode: Image preprocessing strategy ('original', 'enhanced', 'tiled', etc.).
            max_retries: Number of retry attempts on schema/JSON failure.

        Returns:
            PageExtractionResult containing parsed PageContext and raw outputs.
        """
        start_time = time.perf_counter()

        system_prompt = self.get_system_prompt()
        known_cids = set(known_characters.keys()) if known_characters else None

        raw_response: dict[str, Any] = {}
        raw_text = ""
        last_error: Exception | None = None
        attempts = 0
        current_mode = preprocess_mode
        images: list[Image.Image] = []

        for attempt in range(1, max_retries + 2):
            attempts = attempt
            try:
                current_mode = self.select_preprocess_mode(attempt, preprocess_mode, last_error)
                images, segments = self.prepare_images(image_input, current_mode)
                logger.info(
                    f"Page {page_num} attempt {attempt}: mode={current_mode}, "
                    f"sending {len(images)} image(s) sized {[img.size for img in images]}"
                )

                current_prompt = self.build_user_prompt(
                    known_characters, segment_count=len(segments) if segments else None
                )
                if attempt > 1:
                    current_prompt += f"\n\n{self.get_retry_prompt()}"
                    hint = self.build_retry_hint(last_error)
                    if hint:
                        current_prompt += f"\n\n{hint}"

                raw_response = await self._generate(
                    prompt=current_prompt,
                    images=images,
                    system=system_prompt,
                    segmented=segments is not None,
                )

                raw_text = raw_response.get("response", "")
                is_last_attempt = attempt > max_retries
                # Suspicious results trigger a retry; on the last attempt they are
                # kept but flagged for manual review instead of passing silently.
                page_context = ValidationService.validate_page_context(
                    raw_text,
                    page_num=page_num,
                    known_character_ids=known_cids,
                    check_suspicious=not is_last_attempt,
                    flag_suspicious=is_last_attempt,
                    segments=segments,
                )
                if page_context.review_flags:
                    logger.warning(
                        f"Page {page_num} kept for manual review: {'; '.join(page_context.review_flags)}"
                    )
                last_error = None
                break
            except (SchemaValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    f"Extraction attempt {attempt}/{max_retries + 1} failed for page {page_num}: {exc}"
                )
                if attempt > max_retries:
                    raise
            except OllamaError:
                raise

        if last_error:
            raise last_error

        # Persistence (if chapter_id provided)
        raw_path_str: str | None = None
        result_path_str: str | None = None
        if chapter_id:
            raw_path, result_path = self.save_results(
                page_context=page_context,
                raw_response=raw_response,
                chapter_id=chapter_id,
                page_num=page_num,
            )
            raw_path_str = str(raw_path)
            result_path_str = str(result_path)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return PageExtractionResult(
            page_context=page_context,
            raw_response=raw_response,
            raw_text=raw_text,
            processing_time_ms=elapsed_ms,
            attempts=attempts,
            raw_path=raw_path_str,
            result_path=result_path_str,
            preprocess_mode=current_mode,
            image_sizes=[img.size for img in images],
        )
