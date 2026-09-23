"""Unit and integration tests for Phase 6: Character Tracking."""

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
from app.schemas.text_region import TextRegion
from app.services.chapter_service import ChapterService
from app.services.character_service import CharacterService


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
def sample_chapter_with_pages(tmp_path: Path, mock_settings: Settings) -> str:
    chapter_id = "ch-track-1"
    img_dir = tmp_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    dummy = Image.new("RGB", (10, 10))
    for i in range(1, 4):
        dummy.save(img_dir / f"page_{i}.png", format="PNG")

    ch_service = ChapterService(settings=mock_settings)
    ch_service.create_chapter(ChapterCreate(id=chapter_id, title="Tracking Chapter", source_path=str(img_dir)))

    # Save page 1 (c1, c2)
    p1 = PageContext(
        page=1,
        characters=[
            Character(id="c1", description="black-haired man"),
            Character(id="c2", description="blonde woman"),
        ],
        texts=[
            TextRegion(text="Hello", speaker="c1", target="c2", type="sp", order=1),
        ],
    )
    ch_service.save_page_correction(chapter_id, 1, p1)

    # Save page 2 (c1, c3)
    p2 = PageContext(
        page=2,
        characters=[
            Character(id="c1", description="black-haired man"),
            Character(id="c3", description="man with glasses"),
        ],
        texts=[
            TextRegion(text="Who are you?", speaker="c3", target="c1", type="sp", order=1),
        ],
    )
    ch_service.save_page_correction(chapter_id, 2, p2)

    # Save page 3 (c2)
    p3 = PageContext(
        page=3,
        characters=[
            Character(id="c2", description="blonde woman"),
        ],
        texts=[
            TextRegion(text="I'm waiting", speaker="c2", type="sp", order=1),
        ],
    )
    ch_service.save_page_correction(chapter_id, 3, p3)

    return chapter_id


class TestCharacterTrackingService:
    """Tests for CharacterService."""

    def test_get_known_characters_aggregation(
        self, mock_settings: Settings, sample_chapter_with_pages: str
    ):
        service = CharacterService(settings=mock_settings)
        known = service.get_known_characters(sample_chapter_with_pages)

        assert len(known) == 3
        # c1 appears on pages 1 and 2
        c1 = next(c for c in known if c.id == "c1")
        assert c1.occurrences == 2
        assert c1.pages == [1, 2]
        assert c1.first_seen_page == 1
        assert c1.description == "black-haired man"

        # c2 appears on pages 1 and 3
        c2 = next(c for c in known if c.id == "c2")
        assert c2.occurrences == 2
        assert c2.pages == [1, 3]

        # c3 appears on page 2
        c3 = next(c for c in known if c.id == "c3")
        assert c3.occurrences == 1
        assert c3.pages == [2]
        assert c3.first_seen_page == 2

    def test_get_known_characters_dict_for_prompts(
        self, mock_settings: Settings, sample_chapter_with_pages: str
    ):
        service = CharacterService(settings=mock_settings)
        char_dict = service.get_known_characters_dict(sample_chapter_with_pages)

        assert "c1" in char_dict
        assert char_dict["c1"] == "black-haired man"
        assert char_dict["c2"] == "blonde woman"

    def test_rename_character_across_chapter(
        self, mock_settings: Settings, sample_chapter_with_pages: str
    ):
        service = CharacterService(settings=mock_settings)
        ch_service = ChapterService(settings=mock_settings)

        # Rename c1 -> protagonist
        updated = service.rename_character(
            chapter_id=sample_chapter_with_pages,
            old_id="c1",
            new_id="protagonist",
            name="Jin-Woo",
            description="shadow monarch protagonist",
        )

        assert any(c.id == "protagonist" for c in updated)
        assert not any(c.id == "c1" for c in updated)

        # Check page 1 reflects the rename in character and dialogue
        p1 = ch_service.get_page(sample_chapter_with_pages, 1)
        assert p1.context is not None
        assert p1.context.characters[0].id == "protagonist"
        assert p1.context.texts[0].speaker == "protagonist"

        # Check page 2 reflects the rename in dialogue target
        p2 = ch_service.get_page(sample_chapter_with_pages, 2)
        assert p2.context is not None
        assert p2.context.characters[0].id == "protagonist"
        assert p2.context.texts[0].target == "protagonist"

    def test_merge_characters_across_chapter(
        self, mock_settings: Settings, sample_chapter_with_pages: str
    ):
        service = CharacterService(settings=mock_settings)
        ch_service = ChapterService(settings=mock_settings)

        # Merge c3 into c1
        updated = service.merge_characters(
            chapter_id=sample_chapter_with_pages,
            source_id="c3",
            target_id="c1",
            description="black-haired man with glasses",
        )

        assert not any(c.id == "c3" for c in updated)
        c1 = next(c for c in updated if c.id == "c1")
        assert c1.occurrences == 2  # p1 and p2

        # Check page 2: c3 was converted to c1, speaker converted to c1
        p2 = ch_service.get_page(sample_chapter_with_pages, 2)
        assert p2.context is not None
        assert len(p2.context.characters) == 1  # Deduplicated from [c1, c3] -> [c1]
        assert p2.context.characters[0].id == "c1"
        assert p2.context.texts[0].speaker == "c1"


class TestCharacterTrackingAPI:
    """Tests for character tracking REST API."""

    def test_character_api_endpoints(self, tmp_path: Path, mock_settings: Settings):
        settings = get_settings()
        settings.DATA_DIR = tmp_path / "data"
        settings.CHAPTERS_DIR = tmp_path / "data" / "chapters"
        settings.RESULTS_DIR = tmp_path / "data" / "results"
        settings.CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
        settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        with TestClient(app) as client:
            img_dir = tmp_path / "img_api"
            img_dir.mkdir()
            Image.new("RGB", (10, 10)).save(img_dir / "page_1.png")

            client.post("/chapters", json={"id": "ch-api-track", "title": "Track API", "source_path": str(img_dir)})

            # Update page 1
            client.put(
                "/chapters/ch-api-track/pages/1",
                json={
                    "page": 1,
                    "characters": [{"id": "c1", "description": "hero"}, {"id": "c2", "description": "villain"}],
                    "texts": [{"text": "Stop!", "speaker": "c1", "target": "c2", "type": "sp", "order": 1}],
                    "scene": {},
                },
            )

            # 1. GET /chapters/{id}/characters
            res = client.get("/chapters/ch-api-track/characters")
            assert res.status_code == 200
            chars = res.json()
            assert len(chars) == 2

            # 2. POST /chapters/{id}/characters/rename
            res_rename = client.post(
                "/chapters/ch-api-track/characters/rename",
                json={"old_id": "c1", "new_id": "c_hero", "name": "Hero"},
            )
            assert res_rename.status_code == 200
            assert any(c["id"] == "c_hero" for c in res_rename.json())

            # 3. POST /chapters/{id}/characters/merge
            res_merge = client.post(
                "/chapters/ch-api-track/characters/merge",
                json={"source_id": "c2", "target_id": "c_hero"},
            )
            assert res_merge.status_code == 200
            assert not any(c["id"] == "c2" for c in res_merge.json())
