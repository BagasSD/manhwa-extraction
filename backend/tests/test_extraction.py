"""Unit tests for ExtractionService pipeline."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.core.config import Settings
from app.services.extraction_service import ExtractionService
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaService,
    OllamaTimeoutError,
)
from app.services.validation_service import JSONExtractionError, SchemaValidationError


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    results_dir = tmp_path / "data" / "results"
    prompts_dir = tmp_path / "prompts"
    results_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        RESULTS_DIR=results_dir,
        PROMPTS_DIR=prompts_dir,
        OLLAMA_HOST="http://mock-ollama:11434",
        OLLAMA_MODEL="gemma4:31b-cloud",
    )


@pytest.fixture
def sample_image() -> Image.Image:
    return Image.new("RGB", (200, 300), color=(50, 100, 150))


@pytest.mark.asyncio
class TestExtractionService:
    """Tests for single-page extraction pipeline."""

    async def test_extract_page_valid_response(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "model": "gemma4:31b-cloud",
            "response": json.dumps({
                "page": 1,
                "characters": [
                    {
                        "id": "c1",
                        "description": "Hero",
                        "expression": "determined",
                        "emotion": "focus",
                        "action": "holding sword",
                    },
                    {
                        "id": "c2",
                        "description": "Villain",
                        "expression": "smirking",
                        "emotion": "confidence",
                        "action": "standing",
                    },
                ],
                "texts": [
                    {
                        "id": "t1",
                        "text": "This ends now!",
                        "speaker": "c1",
                        "target": "c2",
                        "type": "speech",
                        "order": 1,
                        "confidence": 0.95,
                    },
                    {
                        "id": "t2",
                        "text": "Can he really defeat me?",
                        "speaker": "c2",
                        "target": None,
                        "type": "thought",
                        "order": 2,
                        "confidence": 0.90,
                    },
                ],
                "scene": {
                    "location": "Ruined City",
                    "situation": "c1 confronts c2",
                    "actions": ["c1 points sword at c2"],
                    "mood": "tense",
                },
                "visual_summary": "A hero confronts a villain amidst city ruins.",
            }),
        }

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        result = await service.extract_page(
            image_input=sample_image,
            page_num=1,
            chapter_id="chapter-001",
        )

        assert result.page_context.page == 1
        assert len(result.page_context.characters) == 2
        assert result.page_context.characters[0].id == "c1"
        assert len(result.page_context.texts) == 2
        assert result.page_context.texts[0].id == "t1"
        assert result.page_context.texts[0].text == "This ends now!"
        assert result.page_context.texts[0].type == "speech"
        assert result.page_context.texts[0].speaker == "c1"
        assert result.page_context.texts[0].target == "c2"
        assert result.page_context.texts[1].type == "thought"
        assert result.page_context.scene.location == "Ruined City"
        assert result.page_context.visual_summary == "A hero confronts a villain amidst city ruins."
        assert result.attempts == 1
        assert result.raw_path is not None
        assert result.result_path is not None
        assert Path(result.raw_path).is_file()
        assert Path(result.result_path).is_file()

        # Check saved files content
        saved_raw = json.loads(Path(result.raw_path).read_text(encoding="utf-8"))
        assert "response" in saved_raw
        saved_context = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
        assert saved_context["page"] == 1
        assert saved_context["visual_summary"] == "A hero confronts a villain amidst city ruins."

    async def test_extract_page_with_known_characters(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "model": "gemma4:31b-cloud",
            "response": '{"characters": [{"id": "c1"}], "texts": []}',
        }

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        await service.extract_page(
            image_input=sample_image,
            page_num=2,
            known_characters={"c1": "black-haired man", "c2": "blonde woman"},
        )

        mock_ollama.generate.assert_called_once()
        call_kwargs = mock_ollama.generate.call_args.kwargs
        assert "Known characters:" in call_kwargs["prompt"]
        assert "c1 = black-haired man" in call_kwargs["prompt"]

    async def test_extract_page_retry_on_invalid_json(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        # 1st attempt fails with invalid JSON, 2nd attempt succeeds
        mock_ollama.generate.side_effect = [
            {"model": "gemma4:31b-cloud", "response": "Sorry, I cannot produce JSON."},
            {"model": "gemma4:31b-cloud", "response": '{"characters": [{"id": "c1"}]}'},
        ]

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        result = await service.extract_page(
            image_input=sample_image,
            page_num=3,
            max_retries=1,
        )

        assert result.attempts == 2
        assert len(result.page_context.characters) == 1
        assert mock_ollama.generate.call_count == 2

    async def test_extract_page_retry_on_suspicious_detection(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        # 1st attempt has duplicate text IDs, 2nd attempt fixed
        mock_ollama.generate.side_effect = [
            {
                "model": "gemma4:31b-cloud",
                "response": json.dumps({
                    "characters": [{"id": "c1"}],
                    "texts": [{"id": "t1", "text": "A"}, {"id": "t1", "text": "B"}],
                }),
            },
            {
                "model": "gemma4:31b-cloud",
                "response": json.dumps({
                    "characters": [{"id": "c1"}],
                    "texts": [{"id": "t1", "text": "A"}, {"id": "t2", "text": "B"}],
                }),
            },
        ]

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        result = await service.extract_page(
            image_input=sample_image,
            page_num=4,
            max_retries=1,
        )

        assert result.attempts == 2
        assert len(result.page_context.texts) == 2
        assert result.page_context.texts[0].id == "t1"
        assert result.page_context.texts[1].id == "t2"

    async def test_extract_page_fails_when_all_retries_fail(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "model": "gemma4:31b-cloud",
            "response": "Still not valid JSON",
        }

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        with pytest.raises(JSONExtractionError):
            await service.extract_page(
                image_input=sample_image,
                page_num=5,
                max_retries=1,
            )

    async def test_extract_page_malformed_bbox_fails(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "model": "gemma4:31b-cloud",
            "response": json.dumps({"characters": [{"id": "c1", "bbox": [10, 20]}]}),
        }

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        with pytest.raises(SchemaValidationError):
            await service.extract_page(
                image_input=sample_image,
                page_num=6,
                max_retries=0,
            )

    async def test_extract_page_ollama_connection_failure(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.side_effect = OllamaConnectionError("Cannot connect")

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        with pytest.raises(OllamaConnectionError):
            await service.extract_page(
                image_input=sample_image,
                page_num=7,
            )

    async def test_extract_page_ollama_timeout(
        self, mock_settings: Settings, sample_image: Image.Image
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.side_effect = OllamaTimeoutError("Request timed out")

        service = ExtractionService(settings=mock_settings, ollama_service=mock_ollama)
        with pytest.raises(OllamaTimeoutError):
            await service.extract_page(
                image_input=sample_image,
                page_num=8,
            )
