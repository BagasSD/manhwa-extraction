"""Unit and API tests for Chapter JSON and TXT Export (Phase 9 & UPGRADE_TEXT_EXTRACTION)."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings, get_settings
from app.main import app
from app.models.chapter import ChapterCreate
from app.schemas.chapter_context import (
    ChapterCharacterContext,
    ChapterContext,
    ChapterEvent,
    ChapterTransition,
)
from app.services.chapter_context_service import ChapterContextService
from app.services.chapter_service import ChapterService
from app.services.export_service import ExportService


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
def populated_chapter(tmp_path: Path, mock_settings: Settings) -> str:
    img_dir = tmp_path / "pages"
    img_dir.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (20, 20), color=(150, 150, 150))
    for i in range(1, 3):
        img.save(img_dir / f"page_{i}.png", format="PNG")

    ch_service = ChapterService(settings=mock_settings)
    chapter = ch_service.create_chapter(
        ChapterCreate(id="ch-export-01", title="Episode 1: The Gate", source_path=str(img_dir))
    )

    res_dir = mock_settings.RESULTS_DIR / chapter.id
    res_dir.mkdir(parents=True, exist_ok=True)

    # Page 1
    (res_dir / "page-001.json").write_text(
        json.dumps({
            "page": 1,
            "characters": [
                {
                    "id": "c1",
                    "description": "Black-haired hunter",
                    "expression": "determined",
                    "emotion": "focus",
                    "action": "holding dagger",
                }
            ],
            "texts": [
                {
                    "id": "t1",
                    "text": "I will survive this.",
                    "speaker": "c1",
                    "target": None,
                    "type": "thought",
                    "order": 1,
                }
            ],
            "scene": {
                "location": "D-Rank Dungeon",
                "situation": "Hunter enters dungeon solo",
                "mood": "tense",
                "actions": ["draws weapon"],
            },
            "visual_summary": "A solitary hunter prepares to enter the dungeon.",
        }),
        encoding="utf-8",
    )

    # Page 2
    (res_dir / "page-002.json").write_text(
        json.dumps({
            "page": 2,
            "characters": [
                {"id": "c1", "description": "Black-haired hunter"},
                {"id": "c2", "description": "Goblin chieftain", "action": "screaming"},
            ],
            "texts": [
                {
                    "id": "t1",
                    "text": "Die, human!",
                    "speaker": "c2",
                    "target": "c1",
                    "type": "speech",
                    "order": 1,
                }
            ],
            "scene": {
                "location": "Boss Room",
                "situation": "Confronting goblin boss",
                "actions": ["boss attacks"],
            },
            "visual_summary": "The goblin boss lunges at the hunter.",
        }),
        encoding="utf-8",
    )

    # Persist chapter context
    context_service = ChapterContextService(settings=mock_settings)
    context_service.save_chapter_context(
        chapter.id,
        ChapterContext(
            chapter_id=chapter.id,
            title=chapter.title,
            summary="A hunter enters a D-rank dungeon and confronts the goblin chieftain.",
            characters=[
                ChapterCharacterContext(
                    id="c1",
                    name="Jin-Woo",
                    description="Black-haired hunter",
                    role="protagonist",
                    actions=["enters dungeon", "draws weapon"],
                ),
                ChapterCharacterContext(
                    id="c2",
                    name="Goblin Chief",
                    description="Goblin chieftain",
                    role="antagonist",
                    actions=["attacks hunter"],
                ),
            ],
            events=[
                ChapterEvent(pages=[1], event="Hunter enters the dungeon alone", characters_involved=["c1"]),
                ChapterEvent(pages=[2], event="Hunter confronts the goblin boss", characters_involved=["c1", "c2"]),
            ],
            transitions=[
                ChapterTransition(
                    pages=[1, 2],
                    description="Hunter advances from entry tunnel to boss room",
                    from_location="D-Rank Dungeon",
                    to_location="Boss Room",
                )
            ],
            important_dialogue=[],
        ),
    )

    return chapter.id


class TestExportService:
    """Tests for ExportService JSON and TXT exports."""

    def test_export_json(self, mock_settings: Settings, populated_chapter: str):
        service = ExportService(settings=mock_settings)
        data = service.export_json(populated_chapter, save_to_file=True)

        assert data["chapter_id"] == populated_chapter
        assert data["title"] == "Episode 1: The Gate"
        assert data["total_pages"] == 2
        assert len(data["pages"]) == 2
        assert data["chapter_context"] is not None
        assert data["chapter_context"]["summary"].startswith("A hunter enters")
        assert data["pages"][0]["context"]["visual_summary"] == "A solitary hunter prepares to enter the dungeon."

        # Verify exported file on disk
        export_file = mock_settings.EXPORTS_DIR / f"{populated_chapter}.json"
        assert export_file.is_file()
        persisted = json.loads(export_file.read_text(encoding="utf-8"))
        assert persisted["chapter_id"] == populated_chapter

    def test_export_txt_formatting(self, mock_settings: Settings, populated_chapter: str):
        service = ExportService(settings=mock_settings)
        txt = service.export_txt(populated_chapter, save_to_file=True)

        # Header checks
        assert "CHAPTER: Episode 1: The Gate" in txt
        assert "SUMMARY: A hunter enters a D-rank dungeon" in txt

        # Major events and transitions
        assert "MAJOR EVENTS:" in txt
        assert "[Page 1] Hunter enters the dungeon alone" in txt
        assert "SCENE TRANSITIONS:" in txt
        assert "Hunter advances from entry tunnel to boss room" in txt

        # Character roster
        assert "CHARACTER ROSTER:" in txt
        assert "c1 (Jin-Woo): Black-haired hunter" in txt

        # Page breakdown
        assert "PAGE 1" in txt
        assert "VISUAL SUMMARY: A solitary hunter prepares to enter the dungeon." in txt
        assert "CHARACTERS" in txt
        assert "c1: Black-haired hunter, expression: determined, emotion: focus, action: holding dagger" in txt
        assert '[1] c1 [thought]' in txt
        assert '"I will survive this."' in txt
        assert "Location: D-Rank Dungeon" in txt

        assert "PAGE 2" in txt
        assert "VISUAL SUMMARY: The goblin boss lunges at the hunter." in txt
        assert '[1] c2 → c1' in txt
        assert '"Die, human!"' in txt
        assert "Location: Boss Room" in txt

        # Verify exported file on disk
        export_file = mock_settings.EXPORTS_DIR / f"{populated_chapter}.txt"
        assert export_file.is_file()
        assert export_file.read_text(encoding="utf-8") == txt


class TestExportAPI:
    """Tests for /chapters/{id}/export/json and /chapters/{id}/export/txt routes."""

    def test_export_json_api(self, client: TestClient, populated_chapter: str):
        res = client.get(f"/chapters/{populated_chapter}/export/json")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/json"
        data = res.json()
        assert data["chapter_id"] == populated_chapter
        assert len(data["pages"]) == 2

        # Test download attachment header
        res_dl = client.get(f"/chapters/{populated_chapter}/export/json?download=true")
        assert res_dl.status_code == 200
        assert "attachment" in res_dl.headers.get("content-disposition", "")

    def test_export_txt_api(self, client: TestClient, populated_chapter: str):
        res = client.get(f"/chapters/{populated_chapter}/export/txt")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        assert "CHAPTER: Episode 1: The Gate" in res.text

        # Test download attachment header
        res_dl = client.get(f"/chapters/{populated_chapter}/export/txt?download=true")
        assert res_dl.status_code == 200
        assert "attachment" in res_dl.headers.get("content-disposition", "")

    def test_export_non_existent_chapter_404(self, client: TestClient):
        res_json = client.get("/chapters/unknown-id/export/json")
        assert res_json.status_code == 404

        res_txt = client.get("/chapters/unknown-id/export/txt")
        assert res_txt.status_code == 404
