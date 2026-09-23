"""
Image preprocessing and validation service.

Handles loading, validating dimensions/format, and preprocessing manhwa images
prior to vision model inference (Pillow/OpenCV).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from PIL import Image, ImageEnhance, ImageOps

ImageInput = Union[str, Path, bytes, Image.Image]


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
    def image_to_bytes(cls, image: Image.Image, format: str = "PNG") -> bytes:
        """Convert a PIL Image to raw bytes."""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
