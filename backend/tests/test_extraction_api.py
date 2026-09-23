"""API integration tests for single-page and batch extraction routes."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.main import app
from app.models.chapter import ChapterCreate
from app.services.batch_service import BatchService
from app.services.chapter_service import ChapterService
from app.services.ollama_service import OllamaService


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = get_settings()
    settings.DATA_DIR = tmp_path / "data"
    settings.CHAPTERS_DIR = tmp_path / "data" / "chapters"
    settings.RESULTS_DIR = tmp_path / "data" / "results"
    settings.EXPORTS_DIR = tmp_path / "data" / "exports"
    settings.CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    settings.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Reset BatchService singleton state
    BatchService._instance = None
    BatchService._jobs = {}

    with TestClient(app) as c:
        yield c


@pytest.fixture
def chapter_with_images(tmp_path: Path) -> str:
    img_dir = tmp_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    dummy_img = Image.new("RGB", (30, 30), color=(100, 200, 100))
    for i in range(1, 4):
        dummy_img.save(img_dir / f"page_{i}.png", format="PNG")

    service = ChapterService()
    chapter = service.create_chapter(
        ChapterCreate(id="ch-api-test", title="API Test Chapter", source_path=str(img_dir))
    )
    return chapter.id


def test_batch_extraction_api_flow(client: TestClient, chapter_with_images: str):
    # 1. Check initial status
    resp = client.get(f"/chapters/{chapter_with_images}/extract/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chapter_id"] == chapter_with_images
    assert data["total_pages"] == 3
    assert data["status"] == "idle"

    # 2. Trigger batch extraction
    with patch.object(
        OllamaService,
        "generate",
        new_callable=AsyncMock,
        return_value={
            "response": json.dumps({
                "characters": [{"id": "c1", "description": "Protagonist"}],
                "texts": [{"text": "API Test", "speaker": "c1"}],
                "scene": {"location": "Room"},
            })
        },
    ):
        extract_resp = client.post(
            f"/chapters/{chapter_with_images}/extract",
            json={"skip_completed": True, "force_all": False},
        )
        assert extract_resp.status_code == 200
        extract_data = extract_resp.json()
        assert extract_data["status"] in ("running", "completed")

        # 3. Cancel extraction endpoint
        cancel_resp = client.post(f"/chapters/{chapter_with_images}/extract/cancel")
        assert cancel_resp.status_code == 200


def test_single_page_extract_api(client: TestClient, chapter_with_images: str):
    with patch.object(
        OllamaService,
        "generate",
        new_callable=AsyncMock,
        return_value={
            "response": json.dumps({
                "characters": [{"id": "c1", "description": "Protagonist"}],
                "texts": [{"text": "Single page test", "speaker": "c1"}],
                "scene": {"location": "Dungeon"},
            })
        },
    ):
        resp = client.post(f"/chapters/{chapter_with_images}/pages/1/extract")
        assert resp.status_code == 200
        page_data = resp.json()
        assert page_data["page_number"] == 1
        assert page_data["status"] == "done"
        assert page_data["has_normalized_result"] is True
        assert page_data["context"]["characters"][0]["id"] == "c1"


def test_single_page_retry_api(client: TestClient, chapter_with_images: str):
    with patch.object(
        OllamaService,
        "generate",
        new_callable=AsyncMock,
        return_value={
            "response": json.dumps({
                "characters": [{"id": "c1", "description": "Hero with sword"}],
                "texts": [{"text": "Retried text", "speaker": "c1"}],
                "scene": {"location": "Forest"},
            })
        },
    ):
        resp = client.post(f"/chapters/{chapter_with_images}/pages/2/retry")
        assert resp.status_code == 200
        page_data = resp.json()
        assert page_data["page_number"] == 2
        assert page_data["status"] == "done"
        assert page_data["context"]["scene"]["location"] == "Forest"
