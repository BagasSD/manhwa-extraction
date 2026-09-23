"""Unit tests for ChapterService and page discovery."""

import json
from pathlib import Path
import pytest
from PIL import Image

from app.core.config import Settings
from app.models.chapter import ChapterCreate
from app.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
    InvalidSourceDirectoryError,
    PageNotFoundError,
    natural_sort_key,
)


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
    img_dir = tmp_path / "sample_chapter"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Create 100 sample images: page_1.png ... page_100.png
    dummy_img = Image.new("RGB", (10, 10), color=(100, 150, 200))
    for i in range(1, 101):
        dummy_img.save(img_dir / f"page_{i}.png", format="PNG")

    return img_dir


class TestNaturalSort:
    """Tests for natural numerical sorting helper."""

    def test_natural_sort_ordering(self):
        filenames = ["page_10.png", "page_1.png", "page_2.png", "page_100.png", "page_20.png"]
        sorted_files = sorted(filenames, key=natural_sort_key)
        assert sorted_files == ["page_1.png", "page_2.png", "page_10.png", "page_20.png", "page_100.png"]


class TestChapterService:
    """Tests for chapter lifecycle and page discovery."""

    def test_create_chapter_with_100_images(
        self, mock_settings: Settings, sample_chapter_dir: Path
    ):
        service = ChapterService(settings=mock_settings)
        payload = ChapterCreate(
            id="chapter-001",
            title="Episode 1: The Beginning",
            source_path=str(sample_chapter_dir),
        )

        chapter = service.create_chapter(payload)
        assert chapter.id == "chapter-001"
        assert chapter.title == "Episode 1: The Beginning"
        assert chapter.total_pages == 100
        assert chapter.completed_pages == 0
        assert len(chapter.pages) == 100

        # Verify page ordering: page 1 is page_1.png, page 10 is page_10.png, page 100 is page_100.png
        assert chapter.pages[0].page_number == 1
        assert chapter.pages[0].filename == "page_1.png"
        assert chapter.pages[9].page_number == 10
        assert chapter.pages[9].filename == "page_10.png"
        assert chapter.pages[99].page_number == 100
        assert chapter.pages[99].filename == "page_100.png"

        # Check metadata file existence on disk
        saved_file = mock_settings.CHAPTERS_DIR / "chapter-001.json"
        assert saved_file.is_file()

    def test_create_chapter_empty_directory_fails(
        self, mock_settings: Settings, tmp_path: Path
    ):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        service = ChapterService(settings=mock_settings)
        payload = ChapterCreate(title="Empty Chapter", source_path=str(empty_dir))
        with pytest.raises(InvalidSourceDirectoryError):
            service.create_chapter(payload)

    def test_create_chapter_non_existent_directory_fails(
        self, mock_settings: Settings, tmp_path: Path
    ):
        service = ChapterService(settings=mock_settings)
        payload = ChapterCreate(title="Missing", source_path=str(tmp_path / "does_not_exist"))
        with pytest.raises(InvalidSourceDirectoryError):
            service.create_chapter(payload)

    def test_list_and_get_chapter(
        self, mock_settings: Settings, sample_chapter_dir: Path
    ):
        service = ChapterService(settings=mock_settings)
        service.create_chapter(
            ChapterCreate(id="ch-1", title="Chapter 1", source_path=str(sample_chapter_dir))
        )

        chapters = service.list_chapters()
        assert len(chapters) == 1
        assert chapters[0].id == "ch-1"
        assert chapters[0].total_pages == 100

        fetched = service.get_chapter("ch-1")
        assert fetched.id == "ch-1"
        assert len(fetched.pages) == 100

    def test_get_page_with_persisted_results(
        self, mock_settings: Settings, sample_chapter_dir: Path
    ):
        service = ChapterService(settings=mock_settings)
        service.create_chapter(
            ChapterCreate(id="ch-1", title="Chapter 1", source_path=str(sample_chapter_dir))
        )

        # Simulate extracted page 1 results
        res_dir = mock_settings.RESULTS_DIR / "ch-1"
        res_dir.mkdir(parents=True, exist_ok=True)
        raw_file = res_dir / "page-001.raw.json"
        norm_file = res_dir / "page-001.json"

        raw_file.write_text(json.dumps({"response": "ok"}), encoding="utf-8")
        norm_file.write_text(
            json.dumps({
                "page": 1,
                "characters": [{"id": "c1", "description": "Hero"}],
                "texts": [{"text": "Attack!", "speaker": "c1"}],
                "scene": {"location": "Castle"},
            }),
            encoding="utf-8",
        )

        page_detail = service.get_page("ch-1", 1)
        assert page_detail.page_number == 1
        assert page_detail.status == "done"
        assert page_detail.has_raw_result is True
        assert page_detail.has_normalized_result is True
        assert page_detail.context is not None
        assert page_detail.context.characters[0].id == "c1"

        # Check chapter summary reflects 1 completed page
        chapter = service.get_chapter("ch-1")
        assert chapter.completed_pages == 1

    def test_get_non_existent_page_fails(
        self, mock_settings: Settings, sample_chapter_dir: Path
    ):
        service = ChapterService(settings=mock_settings)
        service.create_chapter(
            ChapterCreate(id="ch-1", title="Chapter 1", source_path=str(sample_chapter_dir))
        )

        with pytest.raises(PageNotFoundError):
            service.get_page("ch-1", 999)

    def test_get_non_existent_chapter_fails(self, mock_settings: Settings):
        service = ChapterService(settings=mock_settings)
        with pytest.raises(ChapterNotFoundError):
            service.get_chapter("unknown-ch")
