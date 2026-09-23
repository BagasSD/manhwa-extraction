"""Unit and API tests for Chapter Context generation and persistence (Phase 8)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings, get_settings
from app.main import app
from app.models.chapter import ChapterCreate
from app.schemas.chapter_context import ChapterContext
from app.services.chapter_context_service import (
    ChapterContextNotFoundError,
    ChapterContextService,
)
from app.services.chapter_service import ChapterService
from app.services.character_service import CharacterService
from app.services.ollama_service import OllamaService


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    chapters_dir = tmp_path / "data" / "chapters"
    results_dir = tmp_path / "data" / "results"
    exports_dir = tmp_path / "data" / "exports"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        CHAPTERS_DIR=chapters_dir,
        RESULTS_DIR=results_dir,
        EXPORTS_DIR=exports_dir,
    )


@pytest.fixture
def client(mock_settings: Settings) -> TestClient:
    settings = get_settings()
    settings.DATA_DIR = mock_settings.DATA_DIR
    settings.CHAPTERS_DIR = mock_settings.CHAPTERS_DIR
    settings.RESULTS_DIR = mock_settings.RESULTS_DIR
    settings.EXPORTS_DIR = mock_settings.EXPORTS_DIR

    with TestClient(app) as c:
        yield c


@pytest.fixture
def chapter_with_extracted_pages(tmp_path: Path, mock_settings: Settings) -> str:
    img_dir = tmp_path / "sample_images"
    img_dir.mkdir(parents=True, exist_ok=True)

    dummy_img = Image.new("RGB", (20, 20), color=(100, 150, 200))
    for i in range(1, 4):
        dummy_img.save(img_dir / f"page_{i}.png", format="PNG")

    ch_service = ChapterService(settings=mock_settings)
    chapter = ch_service.create_chapter(
        ChapterCreate(id="ch-context-01", title="Episode 1: Awakening", source_path=str(img_dir))
    )

    # Populate extracted results for page 1, 2, 3
    res_dir = mock_settings.RESULTS_DIR / chapter.id
    res_dir.mkdir(parents=True, exist_ok=True)

    (res_dir / "page-001.json").write_text(
        json.dumps({
            "page": 1,
            "characters": [{"id": "c1", "description": "Hero with dark cloak", "bbox": [10, 10, 50, 50]}],
            "texts": [{"text": "Where am I?", "speaker": "c1", "bbox": [5, 5, 20, 20]}],
            "scene": {"location": "Dark Forest", "situation": "Hero wakes up lost"},
        }),
        encoding="utf-8",
    )

    (res_dir / "page-002.json").write_text(
        json.dumps({
            "page": 2,
            "characters": [
                {"id": "c1", "description": "Hero with dark cloak", "bbox": [10, 10, 50, 50]},
                {"id": "c2", "description": "Mysterious elder", "bbox": [60, 60, 90, 90]},
            ],
            "texts": [{"text": "Beware the shadow.", "speaker": "c2", "target": "c1"}],
            "scene": {"location": "Dark Forest", "situation": "Elder warns hero"},
        }),
        encoding="utf-8",
    )

    (res_dir / "page-003.json").write_text(
        json.dumps({
            "page": 3,
            "characters": [{"id": "c1", "description": "Hero with dark cloak"}],
            "texts": [{"text": "I will proceed.", "speaker": "c1"}],
            "scene": {"location": "Castle Gates", "situation": "Hero arrives at castle"},
        }),
        encoding="utf-8",
    )

    return chapter.id


class TestChapterContextService:
    """Unit tests for ChapterContextService."""

    def test_prepare_pages_payload_strips_bboxes(
        self, mock_settings: Settings, chapter_with_extracted_pages: str
    ):
        service = ChapterContextService(settings=mock_settings)
        payload = service.prepare_pages_payload(chapter_with_extracted_pages)

        assert payload["chapter_id"] == chapter_with_extracted_pages
        assert payload["title"] == "Episode 1: Awakening"
        assert len(payload["pages"]) == 3

        # Verify bbox is completely removed from characters and texts
        p1 = payload["pages"][0]
        assert "bbox" not in p1["characters"][0]
        assert "bbox" not in p1["texts"][0]

    @pytest.mark.asyncio
    async def test_generate_chapter_context_success(
        self, mock_settings: Settings, chapter_with_extracted_pages: str
    ):
        mock_ollama = AsyncMock(spec=OllamaService)
        mock_ollama.generate.return_value = {
            "response": json.dumps({
                "chapter_id": chapter_with_extracted_pages,
                "title": "Episode 1: Awakening",
                "summary": "The hero wakes up in a dark forest, receives a warning, and arrives at the castle.",
                "characters": [
                    {
                        "id": "c1",
                        "description": "Hero with dark cloak",
                        "role": "protagonist",
                        "actions": ["wakes up", "travels to castle"],
                    },
                    {
                        "id": "c2",
                        "description": "Mysterious elder",
                        "role": "guide",
                        "actions": ["warns hero"],
                    },
                ],
                "events": [
                    {
                        "pages": [1, 2],
                        "event": "Hero awakens in forest and meets mysterious elder",
                        "characters_involved": ["c1", "c2"],
                    },
                    {
                        "pages": [3],
                        "event": "Hero reaches the castle gates",
                        "characters_involved": ["c1"],
                    },
                ],
                "transitions": [
                    {
                        "pages": [2, 3],
                        "description": "Scene transitions from Dark Forest to Castle Gates",
                        "from_location": "Dark Forest",
                        "to_location": "Castle Gates",
                    }
                ],
                "important_dialogue": [
                    {
                        "page": 2,
                        "speaker": "c2",
                        "target": "c1",
                        "text": "Beware the shadow.",
                    }
                ],
            })
        }

        service = ChapterContextService(settings=mock_settings, ollama_service=mock_ollama)
        context = await service.generate_chapter_context(chapter_with_extracted_pages)

        assert context.chapter_id == chapter_with_extracted_pages
        assert len(context.characters) == 2
        assert len(context.events) == 2
        assert len(context.transitions) == 1
        assert len(context.important_dialogue) == 1
        assert context.important_dialogue[0].text == "Beware the shadow."

        # Verify files persisted on disk
        res_dir = mock_settings.RESULTS_DIR / chapter_with_extracted_pages
        assert (res_dir / "context.json").is_file()
        assert (res_dir / "context.raw.json").is_file()

    def test_save_and_get_chapter_context(
        self, mock_settings: Settings, chapter_with_extracted_pages: str
    ):
        service = ChapterContextService(settings=mock_settings)

        # Before creation, should raise not found
        with pytest.raises(ChapterContextNotFoundError):
            service.get_chapter_context(chapter_with_extracted_pages)

        # Save corrected context
        payload = ChapterContext(
            chapter_id=chapter_with_extracted_pages,
            title="Episode 1: Awakening",
            summary="Manual summary",
            characters=[],
            events=[],
            transitions=[],
            important_dialogue=[],
        )
        saved = service.save_chapter_context(chapter_with_extracted_pages, payload)
        assert saved.summary == "Manual summary"

        # Read back
        read = service.get_chapter_context(chapter_with_extracted_pages)
        assert read.summary == "Manual summary"


class TestChapterContextAPI:
    """API endpoints tests for chapter context."""

    def test_chapter_context_api_lifecycle(
        self, client: TestClient, chapter_with_extracted_pages: str
    ):
        # 1. GET context before generation -> 404
        get_res = client.get(f"/chapters/{chapter_with_extracted_pages}/context")
        assert get_res.status_code == 404

        # 2. POST context generation
        with patch.object(
            OllamaService,
            "generate",
            new_callable=AsyncMock,
            return_value={
                "response": json.dumps({
                    "summary": "API Generated Context",
                    "characters": [{"id": "c1", "description": "Hero"}],
                    "events": [{"pages": [1, 3], "event": "Hero journey"}],
                    "transitions": [],
                    "important_dialogue": [],
                })
            },
        ):
            post_res = client.post(f"/chapters/{chapter_with_extracted_pages}/context")
            assert post_res.status_code == 200
            data = post_res.json()
            assert data["summary"] == "API Generated Context"
            assert data["characters"][0]["id"] == "c1"

        # 3. GET context after generation -> 200
        get_after = client.get(f"/chapters/{chapter_with_extracted_pages}/context")
        assert get_after.status_code == 200
        assert get_after.json()["summary"] == "API Generated Context"

        # 4. PUT updated context
        updated_payload = get_after.json()
        updated_payload["summary"] = "User Edited Summary"
        put_res = client.put(
            f"/chapters/{chapter_with_extracted_pages}/context", json=updated_payload
        )
        assert put_res.status_code == 200
        assert put_res.json()["summary"] == "User Edited Summary"
