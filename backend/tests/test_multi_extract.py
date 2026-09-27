"""Unit and integration tests for multi-chapter batch extraction."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.models.batch import MultiChapterExtractRequest
from app.schemas.character import Character
from app.schemas.page_context import PageContext
from app.schemas.scene import Scene
from app.schemas.text_region import TextRegion
from app.services.chapter_service import ChapterService
from app.services.character_service import CharacterService
from app.services.extraction_service import PageExtractionResult
from app.services.multi_chapter_batch_service import (
    MultiChapterAlreadyRunningError,
    MultiChapterBatchService,
)


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.CHAPTERS_DIR = tmp_path / "chapters"
    settings.RESULTS_DIR = tmp_path / "results"
    settings.EXPORTS_DIR = tmp_path / "exports"
    settings.EXTRACTED_IMAGE_DIR = tmp_path / "extracted_images"
    for p in (settings.CHAPTERS_DIR, settings.RESULTS_DIR, settings.EXPORTS_DIR, settings.EXTRACTED_IMAGE_DIR):
        p.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def mock_chapters(test_settings: Settings, tmp_path: Path) -> list[str]:
    """Create 2 dummy chapters with 2 pages each and register them."""
    chapter_service = ChapterService(settings=test_settings)
    chapter_ids = ["ch_01", "ch_02"]
    source_root = tmp_path / "raw_images"
    source_root.mkdir(parents=True, exist_ok=True)

    registered_ids = []
    for cid in chapter_ids:
        ch_dir = source_root / cid
        ch_dir.mkdir(parents=True, exist_ok=True)
        for p in range(1, 3):
            img = Image.new("RGB", (100, 100), color="white")
            img.save(ch_dir / f"page_{p:02d}.jpg")

        from app.models.chapter import ChapterCreate
        created = chapter_service.create_chapter(
            ChapterCreate(id=cid, title=f"Chapter {cid}", source_path=str(ch_dir))
        )
        registered_ids.append(created.id)
    return registered_ids


def test_save_roster_from_dict(test_settings: Settings):
    """Test CharacterService.save_roster_from_dict persists and merges properly."""
    char_service = CharacterService(settings=test_settings)
    chapter_id = "test_chapter"

    char_service.save_roster_from_dict(
        chapter_id,
        {"char_1": "Hero protagonist", "char_2": "Sidekick"},
    )

    known = char_service.get_known_characters(chapter_id)
    assert len(known) == 2
    ids = {k.id for k in known}
    assert "char_1" in ids
    assert "char_2" in ids

    # Merge again with updated description
    char_service.save_roster_from_dict(
        chapter_id,
        {"char_1": "Hero protagonist", "char_3": "Villain"},
    )
    known_updated = char_service.get_known_characters(chapter_id)
    assert len(known_updated) == 3


@pytest.mark.asyncio
async def test_multi_chapter_batch_service_execution(
    test_settings: Settings, mock_chapters: list[str]
):
    """Test MultiChapterBatchService runs through chapters sequentially and shares context."""
    service = MultiChapterBatchService(settings=test_settings)

    # Reset any previous job
    MultiChapterBatchService._current_job = None

    async def fake_extract(image_input, page_num=1, known_characters=None, chapter_id=None, **kwargs):
        # Verify that chapter 2 receives character from chapter 1
        if chapter_id == "ch_02" and page_num == 1:
            assert known_characters is not None
            assert "char_ch_01" in known_characters

        # Return mock result
        cid = f"char_{chapter_id}"
        ctx = PageContext(
            page=page_num,
            characters=[Character(id=cid, description="Extracted char")],
            texts=[TextRegion(id="t1", text="Hello", speaker=cid)],
            scene=Scene(),
        )
        return PageExtractionResult(
            page_context=ctx,
            raw_response={},
            raw_text="",
            processing_time_ms=10.0,
            attempts=1,
        )

    with patch.object(service.extraction_service, "extract_page", side_effect=fake_extract):
        request = MultiChapterExtractRequest(
            chapter_ids=mock_chapters,
            skip_completed=False,
            force_all=True,
        )
        status = service.start_multi_batch(request)
        assert status.status == "running"
        assert status.total_chapters == 2

        # Await completion
        job = MultiChapterBatchService._current_job
        assert job is not None
        if job.task:
            await job.task

        final_status = service.get_status()
        assert final_status.status == "completed"
        assert final_status.completed_chapters == 2
        assert final_status.total_pages_completed == 4

        # Verify shared roster saved back to both chapters
        char_service = CharacterService(settings=test_settings)
        roster_ch1 = {c.id for c in char_service.get_known_characters("ch_01")}
        roster_ch2 = {c.id for c in char_service.get_known_characters("ch_02")}
        assert "char_ch_01" in roster_ch1
        assert "char_ch_02" in roster_ch1
        assert "char_ch_01" in roster_ch2
        assert "char_ch_02" in roster_ch2


def test_multi_extract_api_routes(test_settings: Settings, mock_chapters: list[str]):
    """Test /multi-extract endpoints via TestClient."""
    app = create_app()
    client = TestClient(app)

    MultiChapterBatchService._current_job = None

    # 1. Get status before starting
    res = client.get("/multi-extract/status")
    assert res.status_code == 200
    assert res.json()["status"] == "idle"

    # 2. Start empty request fails validation
    res = client.post("/multi-extract", json={"chapter_ids": []})
    assert res.status_code == 422

    # 3. Cancel when idle returns idle status
    res = client.post("/multi-extract/cancel")
    assert res.status_code == 200
