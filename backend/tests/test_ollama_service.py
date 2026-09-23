"""Unit tests for OllamaService."""

import base64
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    return Settings(
        OLLAMA_HOST="http://mock-ollama:11434",
        OLLAMA_MODEL="gemma4:31b-cloud",
        OLLAMA_THINK=False,
        OLLAMA_TEMPERATURE=0.0,
        OLLAMA_VISUAL_TOKENS=1120,
        OLLAMA_TIMEOUT=10.0,
    )


@pytest.fixture
def sample_pil_image() -> Image.Image:
    # 10x10 RGB test image
    return Image.new("RGB", (10, 10), color=(255, 0, 0))


class TestImageEncoding:
    """Tests for OllamaService.encode_image."""

    def test_encode_from_pil_image(self, sample_pil_image: Image.Image):
        encoded = OllamaService.encode_image(sample_pil_image)
        assert isinstance(encoded, str)
        # Decode to verify it's valid base64
        decoded_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(decoded_bytes))
        assert img.size == (10, 10)

    def test_encode_from_bytes(self):
        raw_bytes = b"fake-image-bytes"
        encoded = OllamaService.encode_image(raw_bytes)
        assert encoded == base64.b64encode(raw_bytes).decode("ascii")

    def test_encode_from_file_path(self, tmp_path: Path, sample_pil_image: Image.Image):
        img_file = tmp_path / "test.png"
        sample_pil_image.save(img_file, format="PNG")

        encoded = OllamaService.encode_image(img_file)
        assert isinstance(encoded, str)
        decoded = base64.b64decode(encoded)
        assert decoded == img_file.read_bytes()

    def test_encode_non_existent_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            OllamaService.encode_image(tmp_path / "does_not_exist.png")

    def test_encode_invalid_type(self):
        with pytest.raises(TypeError):
            OllamaService.encode_image(12345)  # type: ignore


@pytest.mark.asyncio
class TestOllamaServiceAPI:
    """Tests for API communication in OllamaService."""

    async def test_check_connection_success_version(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(200, json={"version": "0.1.30"})

        service = OllamaService(settings=mock_settings, client=mock_client)
        assert await service.check_connection() is True
        mock_client.get.assert_called_once_with("/api/version")

    async def test_check_connection_fallback_tags(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.side_effect = [
            httpx.Response(404),
            httpx.Response(200, json={"models": []}),
        ]

        service = OllamaService(settings=mock_settings, client=mock_client)
        assert await service.check_connection() is True
        assert mock_client.get.call_count == 2

    async def test_check_connection_timeout(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        service = OllamaService(settings=mock_settings, client=mock_client)
        with pytest.raises(OllamaTimeoutError):
            await service.check_connection()

    async def test_check_connection_request_error(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        service = OllamaService(settings=mock_settings, client=mock_client)
        with pytest.raises(OllamaConnectionError):
            await service.check_connection()

    async def test_list_models_success(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            200,
            json={"models": [{"name": "gemma4:31b-cloud"}, {"name": "llama3"}]},
        )

        service = OllamaService(settings=mock_settings, client=mock_client)
        models = await service.list_models()
        assert len(models) == 2
        assert models[0]["name"] == "gemma4:31b-cloud"

    async def test_generate_success(self, mock_settings: Settings, sample_pil_image: Image.Image):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.post.return_value = httpx.Response(
            200,
            json={
                "model": "gemma4:31b-cloud",
                "response": '{"characters": [], "texts": [], "scene": {}}',
                "done": True,
            },
        )

        service = OllamaService(settings=mock_settings, client=mock_client)
        result = await service.generate(
            prompt="Analyze this page.",
            images=[sample_pil_image],
            system="Extract characters and text.",
            format="json",
        )

        assert result["response"] == '{"characters": [], "texts": [], "scene": {}}'
        assert mock_client.post.call_count == 1
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "gemma4:31b-cloud"
        assert call_kwargs["json"]["prompt"] == "Analyze this page."
        assert call_kwargs["json"]["system"] == "Extract characters and text."
        assert call_kwargs["json"]["format"] == "json"
        assert len(call_kwargs["json"]["images"]) == 1

    async def test_generate_404_model_not_found(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.post.return_value = httpx.Response(
            404,
            text='{"error":"model \'gemma4:31b-cloud\' not found"}',
        )

        service = OllamaService(settings=mock_settings, client=mock_client)
        with pytest.raises(OllamaModelNotFoundError) as exc_info:
            await service.generate(prompt="Test")
        assert exc_info.value.status_code == 404

    async def test_generate_500_response_error(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.post.return_value = httpx.Response(500, text="Internal server error")

        service = OllamaService(settings=mock_settings, client=mock_client)
        with pytest.raises(OllamaResponseError) as exc_info:
            await service.generate(prompt="Test")
        assert exc_info.value.status_code == 500

    async def test_generate_timeout_error(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.post.side_effect = httpx.TimeoutException("Read timeout")

        service = OllamaService(settings=mock_settings, client=mock_client)
        with pytest.raises(OllamaTimeoutError):
            await service.generate(prompt="Test")

    async def test_chat_success(self, mock_settings: Settings):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.post.return_value = httpx.Response(
            200,
            json={
                "model": "gemma4:31b-cloud",
                "message": {"role": "assistant", "content": "Hello!"},
                "done": True,
            },
        )

        service = OllamaService(settings=mock_settings, client=mock_client)
        result = await service.chat(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result["message"]["content"] == "Hello!"
        mock_client.post.assert_called_once()

    async def test_async_context_manager(self, mock_settings: Settings):
        async with OllamaService(settings=mock_settings) as service:
            assert isinstance(service, OllamaService)

    async def test_cloud_host_and_api_token_configured(self, tmp_path: Path):
        cloud_settings = Settings(
            OLLAMA_IS_CLOUD=True,
            OLLAMA_API_TOKEN="test-token-123",
            OLLAMA_CLOUD_HOST="https://custom.ollama.cloud",
            OLLAMA_HOST="http://localhost:11434",
            OLLAMA_MODEL="gemma4:31b-cloud",
        )
        service = OllamaService(settings=cloud_settings)
        assert service.is_cloud is True
        assert service.host == "https://custom.ollama.cloud"
        assert service._client.headers.get("authorization") == "Bearer test-token-123"
        await service.close()

    async def test_local_mode_default_no_auth(self, tmp_path: Path):
        local_settings = Settings(
            OLLAMA_IS_CLOUD=False,
            OLLAMA_HOST="http://localhost:11434",
            OLLAMA_MODEL="llama3.2-vision",
        )
        service = OllamaService(settings=local_settings)
        assert service.is_cloud is False
        assert service.host == "http://localhost:11434"
        assert "authorization" not in service._client.headers
        await service.close()

