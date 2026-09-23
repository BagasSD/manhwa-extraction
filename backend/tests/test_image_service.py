"""Unit tests for ImageService."""

from pathlib import Path
import pytest
from PIL import Image

from app.services.image_service import (
    ImageNotFoundError,
    ImageService,
    InvalidImageError,
)


@pytest.fixture
def test_image() -> Image.Image:
    return Image.new("RGB", (100, 200), color=(128, 64, 32))


class TestImageService:
    """Tests for image loading, validation, and preprocessing."""

    def test_load_from_pil(self, test_image: Image.Image):
        loaded = ImageService.load_image(test_image)
        assert loaded.size == (100, 200)

    def test_load_from_file(self, tmp_path: Path, test_image: Image.Image):
        file_path = tmp_path / "test.jpg"
        test_image.save(file_path, format="JPEG")

        loaded = ImageService.load_image(file_path)
        assert loaded.size == (100, 200)

    def test_load_from_bytes(self, test_image: Image.Image):
        raw_bytes = ImageService.image_to_bytes(test_image, format="PNG")
        loaded = ImageService.load_image(raw_bytes)
        assert loaded.size == (100, 200)

    def test_load_non_existent_file(self, tmp_path: Path):
        with pytest.raises(ImageNotFoundError):
            ImageService.load_image(tmp_path / "missing.png")

    def test_load_corrupted_bytes(self):
        with pytest.raises(InvalidImageError):
            ImageService.load_image(b"not an image")

    def test_validate_image(self, test_image: Image.Image):
        width, height = ImageService.validate_image(test_image)
        assert width == 100
        assert height == 200

    @pytest.mark.parametrize("mode", ["original", "grayscale", "contrast", "sharpen", "enhanced", "upscale"])
    def test_preprocessing_modes(self, test_image: Image.Image, mode: str):
        processed = ImageService.preprocess(test_image, mode=mode)
        assert isinstance(processed, Image.Image)
        if mode == "upscale":
            assert processed.size == (200, 400)
        else:
            assert processed.size == (100, 200)

    def test_preprocess_with_max_dimension(self, test_image: Image.Image):
        processed = ImageService.preprocess(test_image, mode="original", max_dimension=100)
        assert max(processed.width, processed.height) <= 100
