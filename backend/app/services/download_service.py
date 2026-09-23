"""
Chapter Download Service.

Fetches manhwa/comic chapters from web URLs, parses image links from HTML or
direct image/zip sources, downloads images concurrently, stores them under
data/chapters/<chapter_id>/, and registers the chapter in ChapterService.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import httpx
from PIL import Image

from app.core.config import Settings, get_settings
from app.models.chapter import Chapter, ChapterCreate
from app.services.chapter_service import ChapterService, natural_sort_key

logger = logging.getLogger(__name__)

# Extensions recognized as manhwa images
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif"}

# Standard browser headers to avoid anti-scraping / hotlink blocks
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}


class DownloadError(Exception):
    """Base exception for chapter download errors."""
    pass


class DownloadService:
    """Service to download chapter images from web URLs and register chapters."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.chapter_service = ChapterService(self.settings)
        self._custom_client = client

    async def download_chapter_from_url(
        self,
        url: str,
        title: str | None = None,
        chapter_id: str | None = None,
        custom_headers: dict[str, str] | None = None,
    ) -> Chapter:
        """Download images from a URL and create a registered Chapter.

        Args:
            url: URL to chapter page, zip file, or direct image.
            title: Optional display title.
            chapter_id: Optional slug identifier.
            custom_headers: Optional HTTP headers override.

        Returns:
            Registered Chapter model populated with discovered pages.
        """
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise DownloadError(f"Invalid URL protocol: {url}")

        headers = dict(DEFAULT_HEADERS)
        parsed_url = urllib.parse.urlparse(url)
        headers["Referer"] = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        if custom_headers:
            headers.update(custom_headers)

        async with (
            self._custom_client
            if self._custom_client
            else httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True)
        ) as client:
            # 1. Fetch the main URL
            try:
                res = await client.get(url)
            except Exception as exc:
                raise DownloadError(f"Failed to fetch URL '{url}': {exc}") from exc

            if res.status_code != 200:
                raise DownloadError(f"Failed to fetch URL '{url}': HTTP {res.status_code}")

            content_type = res.headers.get("content-type", "").lower()
            effective_title = title

            # Determine title if not provided
            if not effective_title:
                effective_title = self._extract_title_from_html(res.text) or parsed_url.path.strip("/").split("/")[-1] or "Downloaded Chapter"

            slug = chapter_id or ChapterService.slugify(effective_title)

            # Target directory in data/chapters/<slug>/
            dest_dir = self.settings.CHAPTERS_DIR / slug
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Case A: ZIP archive
            if "zip" in content_type or url.lower().endswith(".zip") or res.content[:4] == b"PK\x03\x04":
                await self._extract_zip(res.content, dest_dir)
            # Case B: Single direct image
            elif any(content_type.startswith(f"image/{ext.lstrip('.')}") for ext in _IMAGE_EXTENSIONS) or any(url.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
                dest_file = dest_dir / "page-001.png"
                self._save_image_bytes(res.content, dest_file)
            # Case C: HTML Manhwa Reader Page
            else:
                image_urls = self._extract_image_urls_from_html(res.text, base_url=url)
                if not image_urls:
                    raise DownloadError(f"No manhwa images found on page: {url}")

                logger.info(f"Downloading {len(image_urls)} pages from {url} into {dest_dir}")
                await self._download_images(client, image_urls, dest_dir, referer=url)

        # 2. Register chapter
        chapter = self.chapter_service.create_chapter(
            ChapterCreate(
                id=slug,
                title=effective_title,
                source_path=str(dest_dir),
            )
        )
        return chapter

    def _extract_title_from_html(self, html: str) -> str | None:
        """Extract title from HTML <title> or <h1> tag."""
        # Check <title> tag
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            t = title_match.group(1).strip()
            # Clean common suffixes like " - Read Manhwa Online", " | Asura Scans", etc.
            t = re.split(r"[-–|•—]", t)[0].strip()
            if t:
                return t

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
        if h1_match:
            t = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
            if t:
                return t

        return None

    def _extract_image_urls_from_html(self, html: str, base_url: str) -> list[str]:
        """Extract chapter image URLs from reader HTML."""
        found_urls: list[str] = []
        seen: set[str] = set()

        # Match <img> tags and extract source attributes
        # Priority attributes for lazy loaded images commonly used in manhwa sites
        img_tags = re.findall(r"<img\s+[^>]*>", html, re.IGNORECASE)

        for tag in img_tags:
            src = None
            # Check data-src, data-lazy-src, data-original, src, srcset
            for attr in ["data-src", "data-lazy-src", "data-original", "data-url", "src"]:
                match = re.search(rf'{attr}=["\']([^"\']+)["\']', tag, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and not candidate.startswith("data:image"):
                        src = candidate
                        break

            if not src:
                continue

            # Resolve relative URLs
            full_url = urllib.parse.urljoin(base_url, src)

            # Skip small tracking icons, logos, avatars, ads, badges
            lower_url = full_url.lower()
            if any(bad in lower_url for bad in ["logo", "avatar", "icon", "banner", "discord", "ads", "favicon", "pixel", ".svg"]):
                continue

            # Verify plausible image extension or reader path
            parsed = urllib.parse.urlparse(full_url)
            path_ext = Path(parsed.path).suffix.lower()
            if path_ext in _IMAGE_EXTENSIONS or "/chapter" in lower_url or "/manga" in lower_url or "/uploads/" in lower_url:
                if full_url not in seen:
                    seen.add(full_url)
                    found_urls.append(full_url)

        return found_urls

    async def _download_images(
        self,
        client: httpx.AsyncClient,
        image_urls: list[str],
        dest_dir: Path,
        referer: str,
        concurrency: int = 5,
    ) -> None:
        """Download multiple images concurrently and write to dest_dir."""
        semaphore = asyncio.Semaphore(concurrency)
        total_digits = max(3, len(str(len(image_urls))))

        async def fetch_one(idx: int, img_url: str) -> None:
            async with semaphore:
                try:
                    resp = await client.get(
                        img_url,
                        headers={"Referer": referer},
                        timeout=httpx.Timeout(30.0),
                    )
                    if resp.status_code == 200 and len(resp.content) > 100:
                        file_ext = self._detect_or_normalize_ext(resp.content, img_url)
                        file_name = f"page-{idx:0{total_digits}d}{file_ext}"
                        dest_file = dest_dir / file_name
                        self._save_image_bytes(resp.content, dest_file)
                    else:
                        logger.warning(f"Failed to download image {img_url}: HTTP {resp.status_code}")
                except Exception as exc:
                    logger.warning(f"Error downloading image {img_url}: {exc}")

        tasks = [fetch_one(idx, u) for idx, u in enumerate(image_urls, start=1)]
        await asyncio.gather(*tasks)

        # Check if any image was saved
        saved = [p for p in dest_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not saved:
            raise DownloadError(f"Failed to download any valid images from {referer}")

    async def _extract_zip(self, zip_bytes: bytes, dest_dir: Path) -> None:
        """Extract valid image files from a zip archive."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                image_entries = [
                    name for name in zf.namelist()
                    if not name.startswith("__MACOSX") and Path(name).suffix.lower() in _IMAGE_EXTENSIONS
                ]
                image_entries.sort(key=natural_sort_key)
                if not image_entries:
                    raise DownloadError("No valid image files found inside zip archive")

                total_digits = max(3, len(str(len(image_entries))))
                for idx, entry_name in enumerate(image_entries, start=1):
                    raw = zf.read(entry_name)
                    ext = Path(entry_name).suffix.lower() or ".png"
                    dest_file = dest_dir / f"page-{idx:0{total_digits}d}{ext}"
                    self._save_image_bytes(raw, dest_file)
        except zipfile.BadZipFile as exc:
            raise DownloadError("Downloaded file is not a valid zip archive") from exc

    def _detect_or_normalize_ext(self, image_bytes: bytes, img_url: str) -> str:
        """Determine appropriate image file extension from bytes or URL."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                fmt = (img.format or "").lower()
                if fmt in ("jpeg", "jpg"):
                    return ".jpg"
                elif fmt == "png":
                    return ".png"
                elif fmt == "webp":
                    return ".webp"
                elif fmt == "bmp":
                    return ".bmp"
        except Exception:
            pass

        # Fallback to URL extension
        parsed = urllib.parse.urlparse(img_url)
        ext = Path(parsed.path).suffix.lower()
        if ext in _IMAGE_EXTENSIONS:
            return ext
        return ".jpg"

    def _save_image_bytes(self, image_bytes: bytes, dest_file: Path) -> None:
        """Validate and write image bytes to disk."""
        dest_file.write_bytes(image_bytes)
