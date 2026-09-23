"""
Unit tests for DownloadService and POST /chapters/download endpoint.
"""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.models.chapter import ChapterDownloadRequest
from app.services.download_service import DownloadError, DownloadService


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DATA_DIR=tmp_path / "data",
        CHAPTERS_DIR=tmp_path / "data" / "chapters",
        RESULTS_DIR=tmp_path / "data" / "results",
        EXPORTS_DIR=tmp_path / "data" / "exports",
        PROMPTS_DIR=tmp_path / "prompts",
    )


def _make_test_image_bytes(format="PNG", color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", (50, 50), color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.mark.asyncio
class TestDownloadService:
    """Unit tests for DownloadService."""

    async def test_download_invalid_url_protocol(self, tmp_path: Path):
        settings = _make_settings(tmp_path)
        service = DownloadService(settings=settings)
        with pytest.raises(DownloadError) as exc:
            await service.download_chapter_from_url(url="ftp://invalid-url.com")
        assert "Invalid URL protocol" in str(exc.value)

    async def test_download_from_html_page(self, tmp_path: Path):
        settings = _make_settings(tmp_path)
        img1_bytes = _make_test_image_bytes("JPEG", (255, 0, 0))
        img2_bytes = _make_test_image_bytes("PNG", (0, 255, 0))

        html_content = """
        <html>
        <head><title>Solo Leveling Chapter 10 - Read Online</title></head>
        <body>
            <h1>Solo Leveling - Chapter 10</h1>
            <div class="reader">
                <img src="/images/page1.jpg" />
                <img data-src="https://example.com/images/page2.png" />
                <img src="/assets/logo.png" /> <!-- should be ignored -->
            </div>
        </body>
        </html>
        """

        async def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/read/chapter-10":
                return httpx.Response(200, text=html_content, headers={"content-type": "text/html"})
            elif url_str == "https://example.com/images/page1.jpg":
                return httpx.Response(200, content=img1_bytes, headers={"content-type": "image/jpeg"})
            elif url_str == "https://example.com/images/page2.png":
                return httpx.Response(200, content=img2_bytes, headers={"content-type": "image/png"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_client = httpx.AsyncClient(transport=transport)

        service = DownloadService(settings=settings, client=mock_client)
        chapter = await service.download_chapter_from_url(
            url="https://example.com/read/chapter-10",
        )

        assert chapter.title == "Solo Leveling Chapter 10"
        assert chapter.total_pages == 2
        assert len(chapter.pages) == 2
        assert chapter.pages[0].page_number == 1
        assert chapter.pages[1].page_number == 2

        # Verify images written to data/chapters/<slug>/
        dest_dir = settings.CHAPTERS_DIR / chapter.id
        assert dest_dir.is_dir()
        assert len(list(dest_dir.glob("page-*.*"))) == 2

    async def test_download_from_zip_archive(self, tmp_path: Path):
        settings = _make_settings(tmp_path)
        img1_bytes = _make_test_image_bytes("JPEG")
        img2_bytes = _make_test_image_bytes("PNG")

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("01.jpg", img1_bytes)
            zf.writestr("02.png", img2_bytes)
        zip_bytes = zip_buf.getvalue()

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=zip_bytes, headers={"content-type": "application/zip"})

        transport = httpx.MockTransport(handler)
        mock_client = httpx.AsyncClient(transport=transport)

        service = DownloadService(settings=settings, client=mock_client)
        chapter = await service.download_chapter_from_url(
            url="https://example.com/chapter-05.zip",
            title="Chapter 5 Archive",
        )

        assert chapter.title == "Chapter 5 Archive"
        assert chapter.total_pages == 2
        dest_dir = settings.CHAPTERS_DIR / chapter.id
        assert len(list(dest_dir.glob("page-*.*"))) == 2


class TestDownloadAPI:
    """Test REST API endpoint for chapter download."""

    def test_post_download_endpoint(self, tmp_path: Path):
        settings = _make_settings(tmp_path)
        app = create_app()

        img_bytes = _make_test_image_bytes("PNG")
        html_content = '<html><head><title>Chapter 1</title></head><body><img src="https://example.com/p1.png" /></body></html>'

        async def handler(request: httpx.Request) -> httpx.Response:
            if "p1.png" in str(request.url):
                return httpx.Response(200, content=img_bytes, headers={"content-type": "image/png"})
            return httpx.Response(200, text=html_content, headers={"content-type": "text/html"})

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with TestClient(app) as client:
            with patch("app.api.routes.chapters.DownloadService") as MockServiceClass:
                mock_service_instance = DownloadService(settings=settings, client=mock_client)
                MockServiceClass.return_value = mock_service_instance

                response = client.post(
                    "/chapters/download",
                    json={"url": "https://example.com/manga/ch1", "title": "My Downloaded Chapter"},
                )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Downloaded Chapter"
        assert data["total_pages"] == 1
