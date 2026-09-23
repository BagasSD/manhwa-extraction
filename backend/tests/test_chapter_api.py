"""Integration tests for Chapter and Page API endpoints."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = get_settings()
    # Override paths to temporary folder for clean testing
    settings.DATA_DIR = tmp_path / "data"
    settings.CHAPTERS_DIR = tmp_path / "data" / "chapters"
    settings.RESULTS_DIR = tmp_path / "data" / "results"
    settings.CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        yield c


@pytest.fixture
def dummy_image_dir(tmp_path: Path) -> Path:
    img_dir = tmp_path / "raw_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (20, 20), color=(200, 100, 50))
    for i in range(1, 6):
        img.save(img_dir / f"page_{i}.png", format="PNG")
    return img_dir


class TestChapterAPI:
    """Tests for /chapters and /chapters/{id}/pages endpoints."""

    def test_create_and_list_chapters(self, client: TestClient, dummy_image_dir: Path):
        # 1. Create chapter
        payload = {
            "id": "ch-test-1",
            "title": "Test Chapter 1",
            "source_path": str(dummy_image_dir),
        }
        res = client.post("/chapters", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == "ch-test-1"
        assert data["total_pages"] == 5
        assert len(data["pages"]) == 5

        # 2. List chapters
        res_list = client.get("/chapters")
        assert res_list.status_code == 200
        summaries = res_list.json()
        assert len(summaries) == 1
        assert summaries[0]["id"] == "ch-test-1"

        # 3. Get chapter by ID
        res_get = client.get("/chapters/ch-test-1")
        assert res_get.status_code == 200
        assert res_get.json()["total_pages"] == 5

    def test_list_and_get_pages(self, client: TestClient, dummy_image_dir: Path):
        client.post(
            "/chapters",
            json={"id": "ch-test-2", "title": "Test Chapter 2", "source_path": str(dummy_image_dir)},
        )

        # List pages
        res_pages = client.get("/chapters/ch-test-2/pages")
        assert res_pages.status_code == 200
        pages = res_pages.json()
        assert len(pages) == 5
        assert pages[0]["page_number"] == 1
        assert pages[0]["filename"] == "page_1.png"

        # Get single page
        res_page = client.get("/chapters/ch-test-2/pages/1")
        assert res_page.status_code == 200
        page_detail = res_page.json()
        assert page_detail["page_number"] == 1
        assert page_detail["status"] == "pending"

        # Get page image stream
        res_img = client.get("/chapters/ch-test-2/pages/1/image")
        assert res_img.status_code == 200
        assert res_img.headers["content-type"].startswith("image/")

    def test_delete_page_api(self, client: TestClient, dummy_image_dir: Path):
        client.post(
            "/chapters",
            json={"id": "ch-test-del", "title": "Test Delete Page", "source_path": str(dummy_image_dir)},
        )
        # Delete page 2
        res_del = client.delete("/chapters/ch-test-del/pages/2")
        assert res_del.status_code == 200
        updated_ch = res_del.json()
        assert updated_ch["total_pages"] == 4
        assert len(updated_ch["pages"]) == 4
        # Verify contiguous page numbers 1, 2, 3, 4
        assert [p["page_number"] for p in updated_ch["pages"]] == [1, 2, 3, 4]

    def test_not_found_errors(self, client: TestClient):
        res = client.get("/chapters/non-existent")
        assert res.status_code == 404

        res = client.get("/chapters/non-existent/pages")
        assert res.status_code == 404

        res = client.get("/chapters/non-existent/pages/1")
        assert res.status_code == 404

        res = client.delete("/chapters/non-existent/pages/1")
        assert res.status_code == 404

