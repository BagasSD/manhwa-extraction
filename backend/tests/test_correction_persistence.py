"""Unit and integration tests for Phase 5: Manual Correction Persistence."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings, get_settings
from app.main import app
from app.models.chapter import ChapterCreate
from app.schemas.character import Character
from app.schemas.page_context import PageContext
from app.schemas.scene import Scene
from app.schemas.text_region import TextRegion
from app.services.chapter_service import ChapterService


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    chapters_dir = tmp_path / "data" / "chapters"
    results_dir = tmp_path / "data" / "results"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        CHAPTERS_DIR=chapters_dir,
        RESULTS_DIR=results_dir,
    )


@pytest.fixture
def sample_chapter_dir(tmp_path: Path) -> Path:
    img_dir = tmp_path / "chapter_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (10, 10), color=(10, 20, 30))
    for i in range(1, 4):
        img.save(img_dir / f"page_{i}.png", format="PNG")
    return img_dir


class TestCorrectionPersistenceService:
    """Tests for ChapterService.save_page_correction."""

    def test_save_correction_preserves_raw_ai_output(
        self, mock_settings: Settings, sample_chapter_dir: Path
    ):
        service = ChapterService(settings=mock_settings)
        service.create_chapter(
            ChapterCreate(id="ch-corr-1", title="Correction Test", source_path=str(sample_chapter_dir))
        )

        # 1. Setup raw AI output on disk
        res_dir = mock_settings.RESULTS_DIR / "ch-corr-1"
        res_dir.mkdir(parents=True, exist_ok=True)
        raw_file = res_dir / "page-001.raw.json"
        raw_ai_payload = {
            "model": "gemma4:31b-cloud",
            "response": '{"characters":[{"id":"c1"}],"texts":[{"text":"Dont leave!"}]}',
        }
        raw_file.write_text(json.dumps(raw_ai_payload), encoding="utf-8")

        # 2. User makes corrections (e.g. fixed typo "Dont leave!" -> "Don't leave!", added character description)
        corrected_context = PageContext(
            page=1,
            characters=[
                Character(
                    id="c1",
                    description="black-haired protagonist",
                    expression="stern",
                    emotion="determination",
                )
            ],
            texts=[
                TextRegion(
                    text="Don't leave!",
                    speaker="c1",
                    target="c2",
                    type="sp",
                    order=1,
                )
            ],
            scene=Scene(location="Ancient Temple", situation="c1 warns c2 not to step outside"),
        )

        # 3. Save corrections
        page_detail = service.save_page_correction("ch-corr-1", 1, corrected_context)

        # 4. Verify returned PageDetail
        assert page_detail.status == "done"
        assert page_detail.has_normalized_result is True
        assert page_detail.has_raw_result is True
        assert page_detail.context is not None
        assert page_detail.context.texts[0].text == "Don't leave!"
        assert page_detail.context.characters[0].description == "black-haired protagonist"

        # 5. Verify RAW file remains 100% UNCHANGED
        persisted_raw = json.loads(raw_file.read_text(encoding="utf-8"))
        assert persisted_raw == raw_ai_payload

        # 6. Verify reloading from scratch reads the corrected context
        reloaded = service.get_page("ch-corr-1", 1)
        assert reloaded.context is not None
        assert reloaded.context.scene.location == "Ancient Temple"


class TestCorrectionAPI:
    """Tests for PUT /chapters/{id}/pages/{page} endpoint."""

    def test_put_page_correction_api(self, tmp_path: Path, sample_chapter_dir: Path):
        settings = get_settings()
        settings.DATA_DIR = tmp_path / "data"
        settings.CHAPTERS_DIR = tmp_path / "data" / "chapters"
        settings.RESULTS_DIR = tmp_path / "data" / "results"
        settings.CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
        settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        with TestClient(app) as client:
            # Create chapter
            client.post(
                "/chapters",
                json={"id": "ch-api-corr", "title": "API Corr", "source_path": str(sample_chapter_dir)},
            )

            # Update page 1
            put_payload = {
                "page": 1,
                "characters": [{"id": "c1", "description": "Swordsman"}],
                "texts": [{"text": "Stop right there!", "speaker": "c1", "type": "sp", "order": 1}],
                "scene": {"location": "Forest", "situation": "Ambush"},
            }

            res = client.put("/chapters/ch-api-corr/pages/1", json=put_payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "done"
            assert data["context"]["characters"][0]["description"] == "Swordsman"
            assert data["context"]["texts"][0]["text"] == "Stop right there!"

            # Fetch page via GET to confirm persistence
            get_res = client.get("/chapters/ch-api-corr/pages/1")
            assert get_res.status_code == 200
            assert get_res.json()["context"]["scene"]["location"] == "Forest"
