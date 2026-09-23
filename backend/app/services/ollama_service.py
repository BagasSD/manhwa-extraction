"""
Ollama service module for local / cloud vision & LLM inference.

Handles connection, model configuration, image base64 encoding,
request dispatching, response extraction, timeouts, and structured error handling.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Sequence

import httpx
from PIL import Image

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


# =====================================================================
# Custom Exceptions
# =====================================================================

class OllamaError(Exception):
    """Base exception for all Ollama service errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when unable to connect to the Ollama server."""
    pass


class OllamaTimeoutError(OllamaError):
    """Raised when an Ollama request times out."""
    pass


class OllamaResponseError(OllamaError):
    """Raised when Ollama returns an error status code or malformed response."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OllamaModelNotFoundError(OllamaResponseError):
    """Raised when the specified model is not found on the Ollama host."""
    pass


# =====================================================================
# Ollama Service
# =====================================================================

class OllamaService:
    """Service wrapping communication with Ollama API."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.is_cloud = self.settings.OLLAMA_IS_CLOUD
        self.api_token = self.settings.OLLAMA_API_TOKEN or self.settings.OLLAMA_API_KEY

        # If cloud mode is active and host is default localhost, switch to cloud host
        if self.is_cloud and self.settings.OLLAMA_HOST in ("http://localhost:11434", "http://127.0.0.1:11434"):
            self.host = self.settings.OLLAMA_CLOUD_HOST.rstrip("/")
        else:
            self.host = self.settings.OLLAMA_HOST.rstrip("/")

        self.model = self.settings.OLLAMA_MODEL
        self.timeout = self.settings.OLLAMA_TIMEOUT
        self.think = self.settings.OLLAMA_THINK
        self.temperature = self.settings.OLLAMA_TEMPERATURE
        self.visual_tokens = self.settings.OLLAMA_VISUAL_TOKENS

        headers: dict[str, str] = {}
        if self.is_cloud and self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        self._internal_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.host,
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )

    async def __aenter__(self) -> OllamaService:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close underlying httpx client if internally created."""
        if self._internal_client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def encode_image(image_input: str | Path | bytes | Image.Image) -> str:
        """Encode an image to a base64 ASCII string.

        Supports file paths (str / Path), raw image bytes, or PIL Image instances.
        """
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                raise FileNotFoundError(f"Image file not found: {path}")
            raw_bytes = path.read_bytes()
        elif isinstance(image_input, bytes):
            raw_bytes = image_input
        elif isinstance(image_input, Image.Image):
            buffer = io.BytesIO()
            # Preserve format if available, default to PNG
            img_format = image_input.format or "PNG"
            image_input.save(buffer, format=img_format)
            raw_bytes = buffer.getvalue()
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        return base64.b64encode(raw_bytes).decode("ascii")

    def _build_options(self, custom_options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build standard Ollama options dict merged with custom overrides."""
        options: dict[str, Any] = {
            "temperature": self.temperature,
        }
        if custom_options:
            options.update(custom_options)
        return options

    async def check_connection(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            response = await self._client.get("/api/version")
            if response.status_code == 200:
                return True
            # Fallback to /api/tags if /api/version is not 200
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(f"Connection to Ollama timed out at {self.host}") from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(f"Failed to connect to Ollama at {self.host}: {exc}") from exc

    async def list_models(self) -> list[dict[str, Any]]:
        """List models available on the Ollama host."""
        try:
            response = await self._client.get("/api/tags")
            if response.status_code != 200:
                raise OllamaResponseError(
                    f"Failed to list models (HTTP {response.status_code})",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            data = response.json()
            return data.get("models", [])
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(f"Request timed out while listing models from {self.host}") from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(f"Connection error while listing models from {self.host}: {exc}") from exc

    async def generate(
        self,
        prompt: str,
        *,
        images: Sequence[str | Path | bytes | Image.Image] | None = None,
        system: str | None = None,
        model: str | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a generate request to Ollama /api/generate.

        Args:
            prompt: Text prompt to analyze.
            images: List of images (file path, bytes, or PIL Image).
            system: Optional system prompt.
            model: Model override (defaults to configured OLLAMA_MODEL).
            format: 'json' or JSON schema dictionary for structured output.
            options: Additional Ollama runtime options (temperature, num_predict, etc.).
            stream: Whether to stream the response (defaults to False).

        Returns:
            Ollama response dictionary containing 'response' and execution metadata.
        """
        target_model = model or self.model
        encoded_images: list[str] = []
        if images:
            for img in images:
                encoded_images.append(self.encode_image(img))

        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": stream,
            "options": self._build_options(options),
        }

        if system:
            payload["system"] = system
        if encoded_images:
            payload["images"] = encoded_images
        if format is not None:
            payload["format"] = format

        try:
            response = await self._client.post("/api/generate", json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama generate request timed out after {self.timeout}s (model={target_model})"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Failed to communicate with Ollama generate endpoint at {self.host}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{target_model}' not found on Ollama server",
                status_code=404,
                response_body=response.text,
            )
        elif response.status_code != 200:
            raise OllamaResponseError(
                f"Ollama generate failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            return response.json()
        except Exception as exc:
            raise OllamaResponseError(
                f"Failed to decode Ollama response JSON: {exc}",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a chat request to Ollama /api/chat.

        Args:
            messages: List of message objects e.g. [{"role": "user", "content": "...", "images": [...]}]
            model: Model override (defaults to configured OLLAMA_MODEL).
            format: 'json' or JSON schema dictionary.
            options: Additional Ollama runtime options.
            stream: Whether to stream the response (defaults to False).

        Returns:
            Ollama response dictionary containing 'message' and metadata.
        """
        target_model = model or self.model

        # Process any images inside messages that might be paths/PIL images/bytes
        processed_messages: list[dict[str, Any]] = []
        for msg in messages:
            msg_copy = dict(msg)
            if "images" in msg_copy and msg_copy["images"]:
                encoded = []
                for img in msg_copy["images"]:
                    if isinstance(img, str) and not Path(img).is_file() and len(img) > 100:
                        # Likely already base64 string
                        encoded.append(img)
                    else:
                        encoded.append(self.encode_image(img))
                msg_copy["images"] = encoded
            processed_messages.append(msg_copy)

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": processed_messages,
            "stream": stream,
            "options": self._build_options(options),
        }

        if format is not None:
            payload["format"] = format

        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama chat request timed out after {self.timeout}s (model={target_model})"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Failed to communicate with Ollama chat endpoint at {self.host}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{target_model}' not found on Ollama server",
                status_code=404,
                response_body=response.text,
            )
        elif response.status_code != 200:
            raise OllamaResponseError(
                f"Ollama chat failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            return response.json()
        except Exception as exc:
            raise OllamaResponseError(
                f"Failed to decode Ollama chat response JSON: {exc}",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc
