"""Tests for the "Extract Image" pipeline (docs/plan-fitur-panel-crop.md).

Detection runs on synthetic pages whose panel boxes are known; the service and
API tests cover review, the crop-all guard, output naming and isolation from
context extraction. Everything is local: no Ollama involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.core.config import Settings, get_settings
from app.main import app
from app.models.chapter import ChapterCreate
from app.schemas.panel import DetectPanelsRequest
from app.services import panel_store
from app.services.chapter_context_service import ChapterContextService
from app.services.chapter_service import ChapterService
from app.services.panel_service import (
    DetectionParams,
    PanelService,
    PanelsNotReviewedError,
    crop_filename,
    crop_region,
    detect_panels,
    is_text_only,
)

RNG = np.random.default_rng(7)


def _page(width: int, height: int, background: int, boxes: list[tuple[int, int, int, int]]) -> Image.Image:
    """Page with flat `background` gutters and noisy "art" in each (ymin, xmin, ymax, xmax) box."""
    arr = np.full((height, width, 3), background, dtype=np.uint8)
    for ymin, xmin, ymax, xmax in boxes:
        arr[ymin:ymax, xmin:xmax] = RNG.integers(0, 256, size=(ymax - ymin, xmax - xmin, 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def _bboxes(image: Image.Image, **params: object) -> list[list[int]]:
    return [p.bbox for p in detect_panels(image, DetectionParams(**params) if params else None)]


# ---------------------------------------------------------------------------
# detect_panels / crop_region
# ---------------------------------------------------------------------------


class TestDetectPanels:
    @pytest.mark.parametrize("background", [255, 0])
    def test_stacked_panels_on_white_and_black_gutters(self, background: int):
        boxes = [(40, 30, 700, 770), (800, 0, 1500, 800), (1650, 60, 2300, 740)]
        assert _bboxes(_page(800, 2400, background, boxes)) == [list(b) for b in boxes]

    def test_side_by_side_panels_are_split(self):
        boxes = [(50, 20, 600, 380), (50, 420, 600, 780), (700, 20, 1300, 780)]
        assert _bboxes(_page(800, 1400, 255, boxes)) == [list(b) for b in boxes]

    def test_reading_order_numbering(self):
        page = _page(800, 1400, 255, [(700, 20, 1300, 780), (50, 420, 600, 780), (50, 20, 600, 380)])
        panels = detect_panels(page)
        assert [p.panel_index for p in panels] == [1, 2, 3]
        assert [p.bbox[:2] for p in panels] == [[50, 20], [50, 420], [700, 20]]
        assert all(p.status == "auto_detected" and p.image_path is None for p in panels)

    def test_full_bleed_page_is_one_panel(self):
        assert _bboxes(_page(800, 3000, 255, [(0, 0, 3000, 800)])) == [[0, 0, 3000, 800]]

    def test_blank_page_has_no_panels(self):
        assert detect_panels(_page(800, 1200, 255, [])) == []

    def test_tiny_specks_are_ignored(self):
        page = _page(800, 1600, 0, [(100, 50, 700, 750), (900, 400, 920, 420), (1000, 0, 1500, 800)])
        assert _bboxes(page) == [[100, 50, 700, 750], [1000, 0, 1500, 800]]

    def test_thin_blank_line_inside_art_is_not_a_gutter(self):
        page = _page(800, 1200, 255, [(100, 0, 500, 800), (504, 0, 1000, 800)])  # 4px white seam
        assert _bboxes(page) == [[100, 0, 1000, 800]]

    def test_text_only_block_between_panels_is_dropped(self):
        page = _page(800, 2000, 0, [(50, 0, 700, 800), (1200, 0, 1900, 800)])
        draw = ImageDraw.Draw(page)
        draw.rectangle([150, 850, 650, 1050], fill=(255, 255, 255))  # narration box
        draw.text((180, 900), "THEY WERE THE\nFENCE-SITTERS.", fill=(0, 0, 0), font=ImageFont.load_default(size=40))

        assert _bboxes(page) == [[50, 0, 700, 800], [1200, 0, 1900, 800]]

    def test_text_only_classifier(self):
        lettering = Image.new("L", (500, 200), 0)
        ImageDraw.Draw(lettering).text((20, 40), "PERISH.", fill=255, font=ImageFont.load_default(size=90))
        art = RNG.integers(0, 256, size=(200, 500), dtype=np.int16)
        dark_art = RNG.integers(0, 27, size=(200, 500), dtype=np.int16)

        assert is_text_only(np.asarray(lettering, dtype=np.int16))
        assert not is_text_only(art)
        assert not is_text_only(dark_art)

    def test_dark_low_contrast_art_is_kept(self):
        page = _page(800, 1500, 0, [(50, 0, 600, 800)])
        arr = np.asarray(page).copy()
        arr[800:1400] = RNG.integers(0, 27, size=(600, 800, 3), dtype=np.uint8)  # faint night scene
        assert _bboxes(Image.fromarray(arr)) == [[50, 0, 600, 800], [800, 0, 1400, 800]]

    def test_crop_region_is_clamped(self):
        image = _page(100, 200, 255, [])
        assert crop_region(image, [150, 50, 400, 300]).size == (50, 50)
        with pytest.raises(ValueError):
            crop_region(image, [300, 0, 400, 50])


def test_crop_filename_sorts_in_reading_order():
    names = [crop_filename(p, "12", i) for p, i in [(10, 1), (2, 11), (2, 2)]]
    assert names == ["page010-chapter12-crop01.png", "page002-chapter12-crop11.png", "page002-chapter12-crop02.png"]
    assert sorted(names)[0] == "page002-chapter12-crop02.png"


# ---------------------------------------------------------------------------
# PanelService (chapter pipeline)
# ---------------------------------------------------------------------------

PAGE_BOXES = {
    1: [(40, 30, 700, 770), (800, 0, 1500, 800)],
    2: [(50, 20, 600, 380), (50, 420, 600, 780)],
    3: [(0, 0, 900, 600)],
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        CHAPTERS_DIR=tmp_path / "chapters",
        RESULTS_DIR=tmp_path / "results",
        EXPORTS_DIR=tmp_path / "exports",
        DATA_DIR=tmp_path,
        EXTRACTED_IMAGE_DIR=tmp_path / "extractedImage",
    )


def _make_chapter(settings: Settings, tmp_path: Path, chapter_id: str) -> str:
    img_dir = tmp_path / f"{chapter_id}-pages"
    img_dir.mkdir()
    for num, boxes in PAGE_BOXES.items():
        height = 1600 if num == 1 else 900
        _page(800 if num != 3 else 600, height, 255, boxes).save(img_dir / f"page-{num:03d}.png")
    ChapterService(settings=settings).create_chapter(
        ChapterCreate(id=chapter_id, title=chapter_id, source_path=str(img_dir))
    )
    return chapter_id


@pytest.mark.asyncio
class TestPanelService:
    async def test_detection_job_saves_auto_detected_panels(self, settings: Settings, tmp_path: Path):
        chapter_id = _make_chapter(settings, tmp_path, "ch-detect")
        service = PanelService(settings=settings)

        started = service.start_detection(chapter_id)
        assert started.status == "running" and started.total_pages == 3
        job = await service.wait_for_detection(chapter_id)

        assert job.status == "completed"
        assert (job.detected_pages, job.processed_pages, job.failed_pages) == (3, 3, 0)
        page1 = service.get_page_panels(chapter_id, 1)
        assert [p.bbox for p in page1.panels] == [list(b) for b in PAGE_BOXES[1]]
        assert (page1.image_width, page1.image_height, page1.status) == (800, 1600, "auto_detected")
        assert panel_store.panels_path(settings.RESULTS_DIR, chapter_id, 1).is_file()

        chapter = ChapterService(settings=settings).get_chapter(chapter_id)
        assert chapter.image_status == "reviewing"
        assert chapter.context_status == "not_started"  # the two pipelines are independent
        assert (chapter.panel_detected_pages, chapter.panel_reviewed_pages) == (3, 0)
        assert [p.panel_status for p in chapter.pages] == ["auto_detected"] * 3
        assert [p.panel_count for p in chapter.pages] == [2, 2, 1]

    async def test_partial_detection_reports_detecting(self, settings: Settings, tmp_path: Path):
        chapter_id = _make_chapter(settings, tmp_path, "ch-partial")
        service = PanelService(settings=settings)
        service.start_detection(chapter_id, DetectPanelsRequest(pages=[2]))
        job = await service.wait_for_detection(chapter_id)

        assert job.total_pages == 1
        chapter = ChapterService(settings=settings).get_chapter(chapter_id)
        assert chapter.image_status == "detecting"
        assert [p.panel_status for p in chapter.pages] == ["none", "auto_detected", "none"]

    async def test_redetect_keeps_reviewed_pages_unless_overwrite(self, settings: Settings, tmp_path: Path):
        chapter_id = _make_chapter(settings, tmp_path, "ch-redetect")
        service = PanelService(settings=settings)
        service.start_detection(chapter_id)
        await service.wait_for_detection(chapter_id)
        service.save_reviewed_panels(chapter_id, 1, [[10, 10, 100, 100]])

        service.start_detection(chapter_id)
        job = await service.wait_for_detection(chapter_id)
        assert (job.detected_pages, job.skipped_pages) == (2, 1)
        assert [p.bbox for p in service.get_page_panels(chapter_id, 1).panels] == [[10, 10, 100, 100]]

        service.start_detection(chapter_id, DetectPanelsRequest(pages=[1], overwrite_reviewed=True))
        await service.wait_for_detection(chapter_id)
        page1 = service.get_page_panels(chapter_id, 1)
        assert page1.status == "auto_detected" and len(page1.panels) == 2


class TestReviewAndCrop:
    @pytest.fixture
    def detected(self, settings: Settings, tmp_path: Path) -> tuple[PanelService, str]:
        chapter_id = _make_chapter(settings, tmp_path, "ch-crop")
        service = PanelService(settings=settings)
        chapter = service.chapter_service.get_chapter(chapter_id)
        for page in chapter.pages:
            service.detect_page(chapter_id, page)
        return service, chapter_id

    def test_review_renumbers_clamps_and_marks_reviewed(self, detected: tuple[PanelService, str]):
        service, chapter_id = detected
        saved = service.save_reviewed_panels(
            chapter_id, 1, [[800, 0, 1500, 900], [40, 30, 700, 770], [-20, 100, 30, 200]]
        )
        assert saved.status == "reviewed"
        assert [p.panel_index for p in saved.panels] == [1, 2, 3]
        assert [p.bbox for p in saved.panels] == [[0, 100, 30, 200], [40, 30, 700, 770], [800, 0, 1500, 800]]
        assert all(p.status == "reviewed" for p in saved.panels)

    def test_box_outside_page_is_rejected(self, detected: tuple[PanelService, str]):
        service, chapter_id = detected
        with pytest.raises(ValueError):
            service.save_reviewed_panels(chapter_id, 1, [[1700, 0, 1800, 100]])

    def test_crop_all_refuses_unreviewed_pages(self, detected: tuple[PanelService, str]):
        service, chapter_id = detected
        service.save_reviewed_panels(chapter_id, 2, [p.bbox for p in service.get_page_panels(chapter_id, 2).panels])

        with pytest.raises(PanelsNotReviewedError) as exc_info:
            service.crop_all_reviewed(chapter_id)
        assert exc_info.value.unreviewed_pages == [1, 3]
        assert not service.output_dir(chapter_id).exists()

    def test_crop_all_writes_named_pngs(self, detected: tuple[PanelService, str], settings: Settings):
        service, chapter_id = detected
        for num in PAGE_BOXES:
            service.save_reviewed_panels(chapter_id, num, [p.bbox for p in service.get_page_panels(chapter_id, num).panels])

        result = service.crop_all_reviewed(chapter_id)

        assert result.total_crops == 5 and result.pages_cropped == 3
        assert result.files[:2] == ["page001-chapterch-crop-crop01.png", "page001-chapterch-crop-crop02.png"]
        out_dir = settings.EXTRACTED_IMAGE_DIR / chapter_id
        assert Path(result.output_dir) == out_dir.resolve()
        with Image.open(out_dir / "page002-chapterch-crop-crop02.png") as crop:
            assert crop.size == (360, 550)  # [50, 420, 600, 780]
        page2 = service.get_page_panels(chapter_id, 2)
        assert page2.cropped_at and all(Path(p.image_path).is_file() for p in page2.panels)

        chapter = service.chapter_service.get_chapter(chapter_id)
        assert chapter.image_status == "cropped"
        assert [p.panel_status for p in chapter.pages] == ["cropped"] * 3
        assert [i.filename for i in service.list_extracted_images(chapter_id)] == sorted(result.files)

    def test_recrop_removes_stale_files_and_edits_invalidate_crops(self, detected: tuple[PanelService, str]):
        service, chapter_id = detected
        for num in PAGE_BOXES:
            service.save_reviewed_panels(chapter_id, num, [p.bbox for p in service.get_page_panels(chapter_id, num).panels])
        service.crop_all_reviewed(chapter_id)

        # Same boxes again: crops stay valid
        service.save_reviewed_panels(chapter_id, 3, [[0, 0, 900, 600]])
        assert service.chapter_service.get_chapter(chapter_id).image_status == "cropped"

        # Drop a box on page 1: page needs cropping again, and the old crop02 must go
        service.save_reviewed_panels(chapter_id, 1, [[40, 30, 700, 770]])
        assert service.chapter_service.get_chapter(chapter_id).image_status == "reviewing"
        result = service.crop_all_reviewed(chapter_id)
        assert result.total_crops == 4
        assert "page001-chapterch-crop-crop02.png" not in {i.filename for i in service.list_extracted_images(chapter_id)}

    def test_page_without_panels_can_be_reviewed_and_cropped(self, detected: tuple[PanelService, str]):
        service, chapter_id = detected
        service.save_reviewed_panels(chapter_id, 1, [])
        for num in (2, 3):
            service.save_reviewed_panels(chapter_id, num, [p.bbox for p in service.get_page_panels(chapter_id, num).panels])
        result = service.crop_all_reviewed(chapter_id)
        assert result.pages_cropped == 2 and result.total_crops == 3
        assert service.chapter_service.get_chapter(chapter_id).image_status == "cropped"


def test_panel_files_stay_out_of_context_extraction(settings: Settings, tmp_path: Path):
    """Panel data must never be read as page context (page-*.json globs in the chapter folder)."""
    chapter_id = _make_chapter(settings, tmp_path, "ch-isolated")
    service = PanelService(settings=settings)
    for page in service.chapter_service.get_chapter(chapter_id).pages:
        service.detect_page(chapter_id, page)
    res_dir = settings.RESULTS_DIR / chapter_id
    (res_dir / "page-001.json").write_text(json.dumps({"page": 1, "texts": [{"text": "Hi"}]}), encoding="utf-8")

    assert not list(res_dir.glob("page-*.panels.json"))
    payload = ChapterContextService(settings=settings).prepare_pages_payload(chapter_id)
    assert [p["page"] for p in payload["pages"]] == [1]
    chapter = service.chapter_service.get_chapter(chapter_id)
    assert (chapter.context_status, chapter.image_status) == ("extracting", "reviewing")


def test_deleting_a_page_renumbers_its_panels(settings: Settings, tmp_path: Path):
    chapter_id = _make_chapter(settings, tmp_path, "ch-delete")
    service = PanelService(settings=settings)
    for page in service.chapter_service.get_chapter(chapter_id).pages:
        service.detect_page(chapter_id, page)

    service.chapter_service.delete_page(chapter_id, 1)

    moved = panel_store.load_page_panels(settings.RESULTS_DIR, chapter_id, 1)
    assert moved is not None and moved.page == 1 and len(moved.panels) == 2  # former page 2
    assert panel_store.load_page_panels(settings.RESULTS_DIR, chapter_id, 3) is None
    assert [p.panel_count for p in service.chapter_service.get_chapter(chapter_id).pages] == [2, 1]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    live = get_settings()
    for key in ("CHAPTERS_DIR", "RESULTS_DIR", "EXPORTS_DIR", "DATA_DIR", "EXTRACTED_IMAGE_DIR"):
        monkeypatch.setattr(live, key, getattr(settings, key))
    with TestClient(app) as c:
        yield c


def test_panel_api_flow(client: TestClient, settings: Settings, tmp_path: Path):
    chapter_id = _make_chapter(settings, tmp_path, "ch-api")
    base = f"/chapters/{chapter_id}"

    assert client.get(f"{base}/pages/1/panels").status_code == 404
    service = PanelService(settings=settings)
    for page in service.chapter_service.get_chapter(chapter_id).pages:
        service.detect_page(chapter_id, page)

    res = client.get(f"{base}/pages/2/panels")
    assert res.status_code == 200 and len(res.json()["panels"]) == 2

    blocked = client.post(f"{base}/crop-all")
    assert blocked.status_code == 409
    assert blocked.json()["unreviewed_pages"] == [1, 2, 3]

    bad = client.put(f"{base}/pages/1/panels", json={"panels": [{"bbox": [5000, 0, 5100, 10]}]})
    assert bad.status_code == 422

    for num in PAGE_BOXES:
        boxes = [{"bbox": p["bbox"]} for p in client.get(f"{base}/pages/{num}/panels").json()["panels"]]
        saved = client.put(f"{base}/pages/{num}/panels", json={"panels": boxes})
        assert saved.status_code == 200 and saved.json()["status"] == "reviewed"

    cropped = client.post(f"{base}/crop-all")
    assert cropped.status_code == 200 and cropped.json()["total_crops"] == 5

    listing = client.get(f"{base}/extracted-images").json()
    assert [i["filename"] for i in listing][:1] == ["page001-chapterch-api-crop01.png"]
    image = client.get(f"{base}/extracted-images/{listing[0]['filename']}")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get(f"{base}/extracted-images/secret.txt").status_code == 404

    chapter = client.get(base).json()
    assert (chapter["image_status"], chapter["panel_reviewed_pages"]) == ("cropped", 3)
    summary = next(c for c in client.get("/chapters").json() if c["id"] == chapter_id)
    assert summary["image_status"] == "cropped"


def test_detect_panels_api_runs_job(client: TestClient, settings: Settings, tmp_path: Path):
    chapter_id = _make_chapter(settings, tmp_path, "ch-api-job")
    res = client.post(f"/chapters/{chapter_id}/detect-panels", json={"pages": [1]})
    assert res.status_code == 200 and res.json()["status"] in ("running", "completed")

    for _ in range(100):
        status = client.get(f"/chapters/{chapter_id}/detect-panels/status").json()
        if status["status"] != "running":
            break
    else:
        pytest.fail("detection job did not finish")
    assert status["status"] == "completed" and status["detected_pages"] == 1
    assert client.post("/chapters/missing/detect-panels").status_code == 404
