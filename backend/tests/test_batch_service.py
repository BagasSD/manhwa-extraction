"""Unit tests for BatchService, queue processing, resume, retry, and cancellation."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.core.config import Settings
from app.models.batch import BatchExtractRequest
from app.models.chapter import ChapterCreate
from app.schemas.page_context import PageContext
from app.services.batch_service import BatchService
from app.services.chapter_service import ChapterService
from app.services.character_service import CharacterService
from app.services.extraction_service import ExtractionService, PageExtractionResult
from app.services.ollama_service import OllamaService


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    chapters_dir = tmp_path / "data" / "chapters"
    results_dir = tmp_path / "data" / "results"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        CHAPTERS_DIR=chapters_dir,
        RESULTS_DIR=results_dir,
    )


@pytest.fixture
def multi_page_chapter(tmp_path: Path, test_settings: Settings) -> str:
    chapter_dir = tmp_path / "chapter_pages"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    # Create 5 dummy page images
    img = Image.new("RGB", (20, 20), color=(255, 255, 255))
    for i in range(1, 6):
        img.save(chapter_dir / f"page_{i:02d}.png", format="PNG")

    service = ChapterService(settings=test_settings)
    chapter = service.create_chapter(
        ChapterCreate(id="ch-batch-001", title="Batch Test Chapter", source_path=str(chapter_dir))
    )
    return chapter.id


class TestBatchService:
    """Tests for BatchService orchestration."""

    @pytest.mark.asyncio
    async def test_batch_extraction_success(
        self, test_settings: Settings, multi_page_chapter: str
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        # Mock valid JSON response
        mock_ollama.generate.return_value = {
            "response": json.dumps({
                "characters": [{"id": "c1", "description": "Hero"}],
                "texts": [{"text": "Hello world", "speaker": "c1"}],
                "scene": {"location": "City", "situation": "Talking"},
            })
        }

        extraction_service = ExtractionService(settings=test_settings, ollama_service=mock_ollama)
        chapter_service = ChapterService(settings=test_settings)
        character_service = CharacterService(settings=test_settings)

        batch_service = BatchService(
            settings=test_settings,
            extraction_service=extraction_service,
            chapter_service=chapter_service,
            character_service=character_service,
        )

        status = batch_service.start_batch(multi_page_chapter, BatchExtractRequest(skip_completed=True))
        assert status.status == "running"

        # Wait for task to finish
        job = batch_service._jobs[multi_page_chapter]
        if job.task:
            await job.task

        final_status = batch_service.get_batch_status(multi_page_chapter)
        assert final_status.status == "completed"
        assert final_status.completed_pages == 5
        assert final_status.failed_pages == 0
        assert final_status.total_pages == 5

        # Check chapter is marked done for all pages
        ch = chapter_service.get_chapter(multi_page_chapter)
        assert ch.completed_pages == 5
        for p in ch.pages:
            assert p.status == "done"
            assert p.has_normalized_result is True

    @pytest.mark.asyncio
    async def test_batch_resumes_and_skips_completed_pages(
        self, test_settings: Settings, multi_page_chapter: str
    ):
        chapter_service = ChapterService(settings=test_settings)
        
        # Pre-populate page 1 and page 2 as already extracted
        res_dir = test_settings.RESULTS_DIR / multi_page_chapter
        res_dir.mkdir(parents=True, exist_ok=True)
        for page_num in (1, 2):
            (res_dir / f"page-{page_num:03d}.json").write_text(
                json.dumps({
                    "page": page_num,
                    "characters": [{"id": "c1", "description": "Hero"}],
                    "texts": [],
                    "scene": {},
                }),
                encoding="utf-8",
            )

        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "response": json.dumps({
                "characters": [{"id": "c2", "description": "Villain"}],
                "texts": [{"text": "Haha!", "speaker": "c2"}],
                "scene": {"location": "Lair"},
            })
        }

        extraction_service = ExtractionService(settings=test_settings, ollama_service=mock_ollama)
        batch_service = BatchService(
            settings=test_settings,
            extraction_service=extraction_service,
            chapter_service=chapter_service,
        )

        batch_service.start_batch(multi_page_chapter, BatchExtractRequest(skip_completed=True))
        job = batch_service._jobs[multi_page_chapter]
        if job.task:
            await job.task

        final_status = batch_service.get_batch_status(multi_page_chapter)
        assert final_status.status == "completed"
        assert final_status.completed_pages == 5
        # Ollama generate should only be called 3 times (pages 3, 4, 5)
        assert mock_ollama.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_handles_page_failure_without_stopping_entire_batch(
        self, test_settings: Settings, multi_page_chapter: str
    ):
        # Page 3 fails repeatedly, others succeed
        call_count = 0

        async def fake_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # If prompt is for page 3 (or when call 3 happens), return invalid JSON
            prompt = kwargs.get("prompt", "")
            if "page_03" in str(kwargs.get("images", [])) or call_count in (3, 4, 5):
                return {"response": "INVALID JSON"}
            return {
                "response": json.dumps({
                    "characters": [{"id": "c1", "description": "Hero"}],
                    "texts": [{"text": "Valid text"}],
                    "scene": {},
                })
            }

        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.side_effect = fake_generate

        extraction_service = ExtractionService(settings=test_settings, ollama_service=mock_ollama)
        chapter_service = ChapterService(settings=test_settings)
        batch_service = BatchService(
            settings=test_settings,
            extraction_service=extraction_service,
            chapter_service=chapter_service,
        )

        batch_service.start_batch(
            multi_page_chapter,
            BatchExtractRequest(skip_completed=False, max_retries_per_page=1),
        )
        job = batch_service._jobs[multi_page_chapter]
        if job.task:
            await job.task

        final_status = batch_service.get_batch_status(multi_page_chapter)
        assert final_status.status == "completed"
        assert final_status.total_pages == 5
        # 1 page failed, 4 pages completed
        assert final_status.failed_pages >= 1
        assert final_status.completed_pages >= 4

        # Verify page 3 has status manual_review
        p3 = chapter_service.get_page(multi_page_chapter, 3)
        assert p3.status == "manual_review"
        assert p3.error_message is not None

    @pytest.mark.asyncio
    async def test_batch_cancellation(
        self, test_settings: Settings, multi_page_chapter: str
    ):
        mock_ollama = AsyncMock(spec=OllamaService)

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(0.05)
            return {
                "response": json.dumps({
                    "characters": [],
                    "texts": [],
                    "scene": {},
                })
            }

        mock_ollama.generate.side_effect = slow_generate

        extraction_service = ExtractionService(settings=test_settings, ollama_service=mock_ollama)
        batch_service = BatchService(
            settings=test_settings,
            extraction_service=extraction_service,
            chapter_service=ChapterService(settings=test_settings),
        )

        batch_service.start_batch(multi_page_chapter)
        # Immediately request cancel
        cancel_status = batch_service.cancel_batch(multi_page_chapter)
        assert cancel_status.chapter_id == multi_page_chapter

        job = batch_service._jobs[multi_page_chapter]
        if job.task:
            await job.task

        final_status = batch_service.get_batch_status(multi_page_chapter)
        assert final_status.status == "cancelled"

    @pytest.mark.asyncio
    async def test_character_propagation_across_pages(
        self, test_settings: Settings, multi_page_chapter: str
    ):
        prompts_received = []

        async def capture_generate(*args, **kwargs):
            prompt = kwargs.get("prompt", "")
            prompts_received.append(prompt)

            # Page 1 returns character c1
            if len(prompts_received) == 1:
                return {
                    "response": json.dumps({
                        "characters": [{"id": "c1", "description": "Knight in silver armor"}],
                        "texts": [],
                        "scene": {},
                    })
                }
            # Page 2 returns character c2
            elif len(prompts_received) == 2:
                return {
                    "response": json.dumps({
                        "characters": [{"id": "c2", "description": "Mage with blue staff"}],
                        "texts": [],
                        "scene": {},
                    })
                }
            return {
                "response": json.dumps({
                    "characters": [],
                    "texts": [],
                    "scene": {},
                })
            }

        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.side_effect = capture_generate

        extraction_service = ExtractionService(settings=test_settings, ollama_service=mock_ollama)
        batch_service = BatchService(
            settings=test_settings,
            extraction_service=extraction_service,
            chapter_service=ChapterService(settings=test_settings),
            character_service=CharacterService(settings=test_settings),
        )

        batch_service.start_batch(multi_page_chapter)
        job = batch_service._jobs[multi_page_chapter]
        if job.task:
            await job.task

        # Prompt for page 2 should contain c1
        assert "c1 = Knight in silver armor" in prompts_received[1] or "c1=Knight in silver armor" in prompts_received[1]
        # Prompt for page 3 should contain both c1 and c2
        assert "c1 = Knight in silver armor" in prompts_received[2] or "c1=Knight in silver armor" in prompts_received[2]
        assert "c2 = Mage with blue staff" in prompts_received[2] or "c2=Mage with blue staff" in prompts_received[2]
