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

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.schemas.page_context import PageContext
from app.services.image_service import ImageInput, ImageService
from app.services.ollama_service import OllamaError, OllamaService
from app.services.validation_service import (
    JSONExtractionError,
    SchemaValidationError,
    SuspiciousExtractionError,
    ValidationService,
)

logger = logging.getLogger(__name__)


class PageExtractionResult(BaseModel):
    """Result of a single-page extraction operation."""

    page_context: PageContext
    raw_response: dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    processing_time_ms: float = 0.0
    attempts: int = 1
    raw_path: str | None = None
    result_path: str | None = None


class ExtractionService:
    """Service to extract structured page context from a manhwa image."""

    def __init__(
        self,
        settings: Settings | None = None,
        ollama_service: OllamaService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ollama_service = ollama_service or OllamaService(settings=self.settings)

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
            "Extract:\n"
            "- characters\n"
            "- visible text\n"
            "- text type\n"
            "- speaker\n"
            "- target\n"
            "- reading order\n"
            "- facial expression\n"
            "- emotion\n"
            "- action\n"
            "- location\n"
            "- situation\n"
            "- mood\n"
            "- visual summary\n\n"
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

    def build_user_prompt(self, known_characters: dict[str, str] | None = None) -> str:
        """Build the user prompt with optional known characters list."""
        prompt = "Analyze this page."
        if known_characters:
            prompt += "\n\nKnown characters:\n"
            for cid, desc in known_characters.items():
                prompt += f"{cid} = {desc}\n"
        return prompt.strip()

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
        - attempt 2: short retry prompt
        - attempt 3: alternative preprocessing (e.g. 'enhanced') + retry prompt

        Args:
            image_input: Image file path, bytes, or PIL Image.
            page_num: Page number index.
            known_characters: Known character dictionary {id: description}.
            chapter_id: Optional chapter ID to automatically persist results.
            preprocess_mode: Image preprocessing strategy ('original', 'enhanced', etc.).
            max_retries: Number of retry attempts on schema/JSON failure.

        Returns:
            PageExtractionResult containing parsed PageContext and raw outputs.
        """
        start_time = time.perf_counter()

        system_prompt = self.get_system_prompt()
        user_prompt = self.build_user_prompt(known_characters)
        known_cids = set(known_characters.keys()) if known_characters else None

        raw_response: dict[str, Any] = {}
        raw_text = ""
        last_error: Exception | None = None
        attempts = 0

        for attempt in range(1, max_retries + 2):
            attempts = attempt
            try:
                # Select preprocessing mode for attempt
                current_mode = preprocess_mode
                if attempt >= 3:
                    current_mode = "enhanced" if preprocess_mode == "original" else "contrast"

                preprocessed_img = ImageService.preprocess(image_input, mode=current_mode)
                current_prompt = user_prompt if attempt == 1 else f"{user_prompt}\n\n{self.get_retry_prompt()}"

                raw_response = await self.ollama_service.generate(
                    prompt=current_prompt,
                    images=[preprocessed_img],
                    system=system_prompt,
                    format="json",
                )

                raw_text = raw_response.get("response", "")
                is_last_attempt = attempt > max_retries
                # Check suspicious on intermediate attempts to trigger retry, but relax on last attempt
                page_context = ValidationService.validate_page_context(
                    raw_text,
                    page_num=page_num,
                    known_character_ids=known_cids,
                    check_suspicious=not is_last_attempt,
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
        )
