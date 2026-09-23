"""
Image preprocessing and validation service.

Handles loading, validating dimensions/format, and preprocessing manhwa images
prior to vision model inference (Pillow/OpenCV).
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

ImageInput = Union[str, Path, bytes, Image.Image]

# "tiled" mode: a segment is at most this many times taller than it is wide.
# Vision encoders squeeze each image into a fixed budget, so a tall manhwa page
# sent whole leaves its lettering only a few pixels high.
TILE_MAX_ASPECT = 1.5
# Rows averaged when scoring a cut line, so cuts prefer wide blank gutters over
# the thin gaps between lines of text inside one bubble.
_CUT_SMOOTHING_ROWS = 15
# Fraction of the ideal segment height searched around each ideal cut line.
_CUT_SEARCH_FRACTION = 0.25
_MAX_UPSCALE = 3.0


@dataclass
class ImageSegment:
    """One vertical slice of a page, prepared for the vision model."""

    image: Image.Image
    top: int  # y offset of the slice in the original page (pixels)
    height: int  # height of the slice in the original page (pixels)
    page_width: int
    page_height: int

    def to_page_bbox(self, bbox: Sequence[float]) -> list[int]:
        """Map a segment-relative [ymin, xmin, ymax, xmax] box to page-level 0-1000 coordinates.

        Values <= 1000 are read as the model's normalized 0-1000 format, anything
        larger as pixels of the (possibly upscaled) segment image.
        """
        ymin, xmin, ymax, xmax = (float(v) for v in bbox)
        if max(ymin, xmin, ymax, xmax) <= 1000:
            y_scale = self.height / 1000
            x_scale = self.page_width / 1000
        else:
            y_scale = self.height / self.image.height
            x_scale = self.page_width / self.image.width

        def norm_y(y: float) -> int:
            return min(1000, max(0, round((self.top + y * y_scale) / self.page_height * 1000)))

        def norm_x(x: float) -> int:
            return min(1000, max(0, round(x * x_scale / self.page_width * 1000)))

        return [norm_y(ymin), norm_x(xmin), norm_y(ymax), norm_x(xmax)]


class ImageServiceError(Exception):
    """Base exception for image processing errors."""
    pass


class ImageNotFoundError(ImageServiceError, FileNotFoundError):
    """Raised when an image file cannot be found."""
    pass


class InvalidImageError(ImageServiceError, ValueError):
    """Raised when an image is unreadable, corrupted, or unsupported."""
    pass


class ImageService:
    """Service providing image loading, validation, and preprocessing utilities."""

    SUPPORTED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP", "BMP"}

    @classmethod
    def load_image(cls, source: ImageInput) -> Image.Image:
        """Load an image into a PIL Image instance."""
        if isinstance(source, Image.Image):
            return source.copy()

        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                raise ImageNotFoundError(f"Image file not found: {path}")
            try:
                img = Image.open(path)
                img.load()
                return img
            except Exception as exc:
                raise InvalidImageError(f"Failed to open image file '{path}': {exc}") from exc

        if isinstance(source, bytes):
            if not source:
                raise InvalidImageError("Image byte content is empty")
            try:
                img = Image.open(io.BytesIO(source))
                img.load()
                return img
            except Exception as exc:
                raise InvalidImageError(f"Failed to decode image from bytes: {exc}") from exc

        raise InvalidImageError(f"Unsupported image input type: {type(source)}")

    @classmethod
    def validate_image(cls, source: ImageInput) -> tuple[int, int]:
        """Validate image readable state and return (width, height)."""
        img = cls.load_image(source)
        if img.width <= 0 or img.height <= 0:
            raise InvalidImageError(f"Invalid image dimensions: {img.width}x{img.height}")
        return img.width, img.height

    @classmethod
    def preprocess(
        cls,
        image: ImageInput,
        mode: str = "original",
        max_dimension: int | None = None,
    ) -> Image.Image:
        """Preprocess an image according to specified strategy mode.

        Supported modes: 'original', 'grayscale', 'contrast', 'sharpen', 'enhanced', 'upscale'.
        """
        img = cls.load_image(image)

        # Convert palette/transparency to standard RGB
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        mode_clean = mode.strip().lower()

        if mode_clean == "original":
            pass
        elif mode_clean == "grayscale":
            img = ImageOps.grayscale(img).convert("RGB")
        elif mode_clean == "contrast":
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
        elif mode_clean == "sharpen":
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.5)
        elif mode_clean == "enhanced":
            # Combined contrast and sharpness boost
            contrast_enhancer = ImageEnhance.Contrast(img)
            img = contrast_enhancer.enhance(1.25)
            sharp_enhancer = ImageEnhance.Sharpness(img)
            img = sharp_enhancer.enhance(1.3)
        elif mode_clean == "upscale":
            # 2x upscale using BICUBIC/LANCZOS
            img = img.resize((img.width * 2, img.height * 2), resample=Image.Resampling.LANCZOS)
        else:
            # Unknown mode, keep original
            pass

        # Optional maximum dimension constrain
        if max_dimension and max(img.width, img.height) > max_dimension:
            scale = max_dimension / max(img.width, img.height)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

        return img

    @classmethod
    def split_into_segments(
        cls,
        image: ImageInput,
        max_segments: int = 8,
        min_width: int = 1024,
    ) -> list[ImageSegment]:
        """Split a page into top-to-bottom segments and upscale narrow ones ("tiled" mode).

        Pages taller than TILE_MAX_ASPECT x width are cut into roughly equal
        slices, each cut placed on the most uniform band of rows (panel gutter)
        near its ideal position so speech bubbles are not sliced through. Slices
        narrower than `min_width` are upscaled (at most 3x) so small lettering
        survives the model's own downscaling.
        """
        img = cls.load_image(image)
        if img.mode != "RGB":
            img = img.convert("RGB")
        width, height = img.size

        count = max(1, min(max_segments, math.ceil(height / (width * TILE_MAX_ASPECT))))
        bounds = [0, *cls._find_cut_rows(img, count), height]

        factor = min(_MAX_UPSCALE, max(1.0, min_width / width))
        segments: list[ImageSegment] = []
        for top, bottom in zip(bounds, bounds[1:]):
            crop = img.crop((0, top, width, bottom))
            if factor > 1.0:
                crop = crop.resize(
                    (round(width * factor), round((bottom - top) * factor)),
                    resample=Image.Resampling.LANCZOS,
                )
            segments.append(
                ImageSegment(
                    image=crop,
                    top=top,
                    height=bottom - top,
                    page_width=width,
                    page_height=height,
                )
            )
        return segments

    @staticmethod
    def _find_cut_rows(img: Image.Image, count: int) -> list[int]:
        """Pick `count - 1` cut rows, each on the calmest band near its ideal position."""
        if count <= 1:
            return []

        gray = np.asarray(ImageOps.grayscale(img), dtype=np.float32)
        height = gray.shape[0]
        # Row "busyness": mean horizontal gradient. Blank gutters and flat
        # panel borders score ~0; lettering and line art score high.
        row_cost = np.abs(np.diff(gray, axis=1)).mean(axis=1)
        kernel = np.ones(_CUT_SMOOTHING_ROWS, dtype=np.float32) / _CUT_SMOOTHING_ROWS
        smoothed = np.convolve(row_cost, kernel, mode="same")

        ideal_height = height / count
        radius = max(1, int(ideal_height * _CUT_SEARCH_FRACTION))
        cuts: list[int] = []
        previous = 0
        for i in range(1, count):
            ideal = int(round(ideal_height * i))
            lo = max(previous + 1, ideal - radius)
            hi = min(height - 1, ideal + radius)
            if lo >= hi:
                cut = min(max(ideal, previous + 1), height - 1)
            else:
                window = smoothed[lo:hi]
                candidates = np.flatnonzero(window <= window.min() + 1e-6) + lo
                # Among equally calm rows, stay closest to the ideal cut.
                cut = int(candidates[np.argmin(np.abs(candidates - ideal))])
            cuts.append(cut)
            previous = cut
        return cuts

    @classmethod
    def image_to_bytes(cls, image: Image.Image, format: str = "PNG") -> bytes:
        """Convert a PIL Image to raw bytes."""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
