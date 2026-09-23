"""
Unit tests for BenchmarkService — Phase 10.

All Ollama calls are mocked. Tests cover:
  - Successful benchmark run across multiple modes
  - Per-mode summary aggregation
  - Recommended mode selection logic
  - Handling fixture directories with no images
  - Handling extraction failures
  - Persistence (save/load)
  - REST endpoints (POST /benchmark/run, GET /benchmark/results, GET /benchmark/results/{id})
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.schemas.benchmark import (
    BenchmarkRunRequest,
    BenchmarkRunResult,
    BenchmarkStatus,
    ModeSummary,
    PageBenchmarkResult,
    PreprocessMode,
)
from app.services.benchmark_service import BenchmarkService
from app.services.ollama_service import OllamaConnectionError, OllamaService
from app.services.validation_service import JSONExtractionError


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

_VALID_PAGE_JSON = json.dumps(
    {
        "page": 1,
        "characters": [{"id": "c1", "description": "black-haired man"}],
        "texts": [{"text": "Don't leave!", "speaker": "c1", "type": "sp"}],
        "scene": {"location": "forest", "situation": "c1 calls out to c2"},
    }
)

_VALID_OLLAMA_RESPONSE: dict[str, Any] = {
    "model": "gemma4:31b-cloud",
    "response": _VALID_PAGE_JSON,
}


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        RESULTS_DIR=tmp_path / "results",
        PROMPTS_DIR=tmp_path / "prompts",
        DATA_DIR=tmp_path / "data",
        CHAPTERS_DIR=tmp_path / "chapters",
        EXPORTS_DIR=tmp_path / "exports",
        OLLAMA_HOST="http://mock-ollama:11434",
        OLLAMA_MODEL="gemma4:31b-cloud",
    )


def _create_fixture_image(directory: Path, name: str = "page-001.png") -> Path:
    """Create a small synthetic PNG in the given directory."""
    directory.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 150), color=(200, 210, 220))
    path = directory / name
    img.save(path, format="PNG")
    return path


def _mock_ollama(response: dict | list[dict] | Exception) -> AsyncMock:
    """Build a mock OllamaService.generate that returns/raises the given value."""
    mock = AsyncMock(spec=OllamaService)
    if isinstance(response, Exception):
        mock.generate.side_effect = response
    elif isinstance(response, list):
        mock.generate.side_effect = response
    else:
        mock.generate.return_value = response
    return mock


# ---------------------------------------------------------------------------
# BenchmarkService unit tests
# ---------------------------------------------------------------------------


class TestBenchmarkServiceCollect:
    """Tests for _collect_fixtures."""

    def test_collect_empty_directory(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        fixture_dir = tmp_path / "fixtures_empty"
        fixture_dir.mkdir()
        images = service._collect_fixtures(fixture_dir, max_pages=None)
        assert images == []

    def test_collect_missing_directory(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        fixture_dir = tmp_path / "does_not_exist"
        images = service._collect_fixtures(fixture_dir, max_pages=None)
        assert images == []

    def test_collect_flat_images(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        fixture_dir = tmp_path / "fixtures"
        for name in ("a.png", "b.jpg", "readme.txt"):
            (fixture_dir).mkdir(exist_ok=True)
            (fixture_dir / name).write_bytes(b"")
        images = service._collect_fixtures(fixture_dir, max_pages=None)
        # Only PNG and JPG should be collected
        assert len(images) == 2

    def test_collect_subdirectory_images(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        fixture_dir = tmp_path / "fixtures"
        sub = fixture_dir / "clean"
        sub.mkdir(parents=True)
        (sub / "p1.png").write_bytes(b"")
        (sub / "p2.png").write_bytes(b"")
        images = service._collect_fixtures(fixture_dir, max_pages=None)
        assert len(images) == 2

    def test_collect_respects_max_pages(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        fixture_dir = tmp_path / "fixtures"
        sub = fixture_dir / "clean"
        sub.mkdir(parents=True)
        for i in range(5):
            (sub / f"p{i:02d}.png").write_bytes(b"")
        images = service._collect_fixtures(fixture_dir, max_pages=3)
        assert len(images) == 3


class TestBenchmarkServiceStatistics:
    """Tests for summary computation and recommended mode selection."""

    def _make_page_result(
        self,
        mode: PreprocessMode,
        success: bool,
        time_ms: float,
        attempts: int = 1,
        characters: int = 0,
        texts: int = 0,
    ) -> PageBenchmarkResult:
        return PageBenchmarkResult(
            page_path="page-001.png",
            mode=mode,
            success=success,
            processing_time_ms=time_ms,
            attempts=attempts,
            character_count=characters,
            text_count=texts,
        )

    def test_mode_summary_all_success(self) -> None:
        results = [
            self._make_page_result(PreprocessMode.ORIGINAL, True, 1000.0, 1, 2, 3),
            self._make_page_result(PreprocessMode.ORIGINAL, True, 2000.0, 1, 1, 2),
        ]
        summary = BenchmarkService._compute_mode_summary(PreprocessMode.ORIGINAL, results)
        assert summary.total_pages == 2
        assert summary.success_count == 2
        assert summary.failure_count == 0
        assert summary.json_validity_rate == 1.0
        assert summary.avg_processing_time_ms == pytest.approx(1500.0)
        assert summary.retry_rate == 0.0

    def test_mode_summary_mixed_success_failure(self) -> None:
        results = [
            self._make_page_result(PreprocessMode.ENHANCED, True, 1000.0, 1),
            self._make_page_result(PreprocessMode.ENHANCED, False, 2000.0, 3),
            self._make_page_result(PreprocessMode.ENHANCED, True, 1500.0, 2),
        ]
        summary = BenchmarkService._compute_mode_summary(PreprocessMode.ENHANCED, results)
        assert summary.total_pages == 3
        assert summary.success_count == 2
        assert summary.failure_count == 1
        assert summary.json_validity_rate == pytest.approx(2 / 3, rel=1e-3)
        assert summary.retry_rate == pytest.approx(2 / 3, rel=1e-3)  # 2 needed retries (attempts>1)

    def test_mode_summary_empty(self) -> None:
        summary = BenchmarkService._compute_mode_summary(PreprocessMode.GRAYSCALE, [])
        assert summary.total_pages == 0
        assert summary.json_validity_rate == 0.0

    def test_mode_summary_filters_by_mode(self) -> None:
        results = [
            self._make_page_result(PreprocessMode.ORIGINAL, True, 500.0),
            self._make_page_result(PreprocessMode.ENHANCED, False, 800.0),
        ]
        summary = BenchmarkService._compute_mode_summary(PreprocessMode.ORIGINAL, results)
        assert summary.total_pages == 1
        assert summary.success_count == 1

    def test_recommended_mode_picks_highest_validity(self) -> None:
        s1 = ModeSummary(
            mode=PreprocessMode.ORIGINAL,
            total_pages=5,
            success_count=3,
            failure_count=2,
            json_validity_rate=0.60,
            avg_processing_time_ms=1000.0,
            total_processing_time_ms=5000.0,
            avg_attempts=1.5,
            avg_character_count=2.0,
            avg_text_count=3.0,
            retry_rate=0.4,
        )
        s2 = ModeSummary(
            mode=PreprocessMode.ENHANCED,
            total_pages=5,
            success_count=5,
            failure_count=0,
            json_validity_rate=1.00,
            avg_processing_time_ms=1500.0,
            total_processing_time_ms=7500.0,
            avg_attempts=1.0,
            avg_character_count=2.5,
            avg_text_count=3.5,
            retry_rate=0.0,
        )
        recommended = BenchmarkService._pick_recommended_mode([s1, s2])
        assert recommended == PreprocessMode.ENHANCED

    def test_recommended_mode_breaks_tie_by_speed(self) -> None:
        s1 = ModeSummary(
            mode=PreprocessMode.ORIGINAL,
            total_pages=2,
            success_count=2,
            failure_count=0,
            json_validity_rate=1.0,
            avg_processing_time_ms=500.0,
            total_processing_time_ms=1000.0,
            avg_attempts=1.0,
            avg_character_count=1.0,
            avg_text_count=1.0,
            retry_rate=0.0,
        )
        s2 = ModeSummary(
            mode=PreprocessMode.GRAYSCALE,
            total_pages=2,
            success_count=2,
            failure_count=0,
            json_validity_rate=1.0,
            avg_processing_time_ms=900.0,
            total_processing_time_ms=1800.0,
            avg_attempts=1.0,
            avg_character_count=1.0,
            avg_text_count=1.0,
            retry_rate=0.0,
        )
        recommended = BenchmarkService._pick_recommended_mode([s1, s2])
        # Both have 100% validity — pick the faster one (ORIGINAL)
        assert recommended == PreprocessMode.ORIGINAL

    def test_recommended_mode_returns_none_when_no_pages(self) -> None:
        summaries = [
            ModeSummary(
                mode=PreprocessMode.ORIGINAL,
                total_pages=0,
                success_count=0,
                failure_count=0,
                json_validity_rate=0.0,
                avg_processing_time_ms=0.0,
                total_processing_time_ms=0.0,
                avg_attempts=1.0,
                avg_character_count=0.0,
                avg_text_count=0.0,
                retry_rate=0.0,
            )
        ]
        assert BenchmarkService._pick_recommended_mode(summaries) is None


@pytest.mark.asyncio
class TestBenchmarkServiceRun:
    """End-to-end BenchmarkService.run() tests with mocked Ollama."""

    async def test_run_no_fixtures(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings, ollama_service=_mock_ollama(_VALID_OLLAMA_RESPONSE))
        empty_dir = tmp_path / "empty_fixtures"
        empty_dir.mkdir()
        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(empty_dir),
        )
        result = await service.run(request)
        assert result.status == BenchmarkStatus.DONE
        assert result.total_fixtures == 0
        assert result.page_results == []
        assert result.recommended_mode is None

    async def test_run_single_image_single_mode(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)

        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
        )
        result = await service.run(request)

        assert result.status == BenchmarkStatus.DONE
        assert result.total_fixtures == 1
        assert len(result.page_results) == 1
        assert result.page_results[0].success is True
        assert result.page_results[0].mode == PreprocessMode.ORIGINAL
        assert result.page_results[0].character_count == 1
        assert result.page_results[0].text_count == 1
        assert result.mode_summaries[0].json_validity_rate == 1.0
        assert result.recommended_mode == PreprocessMode.ORIGINAL

    async def test_run_multiple_modes(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)
        _create_fixture_image(fixture_dir, "page-002.png")

        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL, PreprocessMode.ENHANCED, PreprocessMode.GRAYSCALE],
            fixture_dir=str(fixture_dir),
        )
        result = await service.run(request)

        # 2 images × 3 modes = 6 page results
        assert len(result.page_results) == 6
        assert len(result.mode_summaries) == 3
        for summary in result.mode_summaries:
            assert summary.total_pages == 2
            assert summary.json_validity_rate == 1.0

    async def test_run_respects_max_pages(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        for i in range(5):
            _create_fixture_image(fixture_dir, f"p{i:02d}.png")

        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
            max_pages=2,
        )
        result = await service.run(request)
        assert result.total_fixtures == 2
        assert len(result.page_results) == 2

    async def test_run_extraction_failure_recorded(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)

        # All extraction attempts return bad JSON → extraction fails
        bad_response = {"model": "gemma4:31b-cloud", "response": "not json at all"}
        mock = _mock_ollama(bad_response)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
        )
        result = await service.run(request)

        assert result.page_results[0].success is False
        assert result.page_results[0].error is not None
        assert result.mode_summaries[0].json_validity_rate == 0.0

    async def test_run_ollama_error_recorded(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)

        mock = _mock_ollama(OllamaConnectionError("cannot connect"))
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
        )
        result = await service.run(request)

        assert result.page_results[0].success is False
        assert "OllamaError" in result.page_results[0].error

    async def test_run_persists_result_to_disk(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)

        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
        )
        result = await service.run(request)

        benchmark_dir = settings.DATA_DIR / "benchmarks"
        saved_files = list(benchmark_dir.glob("*.json"))
        assert len(saved_files) == 1
        loaded = json.loads(saved_files[0].read_text(encoding="utf-8"))
        assert loaded["run_id"] == result.run_id

    async def test_load_results_returns_saved_runs(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        fixture_dir = tmp_path / "fixtures"
        _create_fixture_image(fixture_dir)

        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)
        service = BenchmarkService(settings=settings, ollama_service=mock)

        request = BenchmarkRunRequest(
            modes=[PreprocessMode.ORIGINAL],
            fixture_dir=str(fixture_dir),
        )
        run1 = await service.run(request)
        run2 = await service.run(request)

        all_results = service.load_results()
        assert len(all_results) == 2
        run_ids = {r["run_id"] for r in all_results}
        assert run1.run_id in run_ids
        assert run2.run_id in run_ids

    async def test_load_results_empty_when_no_dir(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        service = BenchmarkService(settings=settings)
        results = service.load_results()
        assert results == []


# ---------------------------------------------------------------------------
# REST endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a TestClient with patched settings and mocked BenchmarkService."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    """Create a fixture directory with one synthetic image."""
    d = tmp_path / "fixtures"
    _create_fixture_image(d)
    return d


class TestBenchmarkAPI:
    """Integration tests for benchmark REST endpoints."""

    def test_run_benchmark_success(self, tmp_path: Path, fixture_dir: Path) -> None:
        settings = _make_settings(tmp_path)
        mock = _mock_ollama(_VALID_OLLAMA_RESPONSE)

        app = create_app()
        with TestClient(app) as client:
            with (
                patch(
                    "app.api.routes.benchmark._get_service",
                    return_value=BenchmarkService(settings=settings, ollama_service=mock),
                )
            ):
                response = client.post(
                    "/benchmark/run",
                    json={
                        "modes": ["original"],
                        "fixture_dir": str(fixture_dir),
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["total_fixtures"] == 1
        assert len(data["page_results"]) == 1
        assert data["page_results"][0]["success"] is True

    def test_run_benchmark_empty_fixture_dir(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        app = create_app()
        with TestClient(app) as client:
            with patch(
                "app.api.routes.benchmark._get_service",
                return_value=BenchmarkService(settings=settings),
            ):
                response = client.post(
                    "/benchmark/run",
                    json={
                        "modes": ["original"],
                        "fixture_dir": str(empty_dir),
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["total_fixtures"] == 0

    def test_list_benchmark_results(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        # Seed a fake result file
        bdir = settings.DATA_DIR / "benchmarks"
        bdir.mkdir(parents=True)
        fake = {"run_id": "abc123", "status": "done", "total_fixtures": 1}
        (bdir / "benchmark-abc123.json").write_text(json.dumps(fake), encoding="utf-8")

        app = create_app()
        with TestClient(app) as client:
            with patch(
                "app.api.routes.benchmark._get_service",
                return_value=BenchmarkService(settings=settings),
            ):
                response = client.get("/benchmark/results")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["run_id"] == "abc123"

    def test_get_specific_benchmark_result(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        bdir = settings.DATA_DIR / "benchmarks"
        bdir.mkdir(parents=True)
        fake = {"run_id": "xyz789", "status": "done", "total_fixtures": 2}
        (bdir / "benchmark-xyz789.json").write_text(json.dumps(fake), encoding="utf-8")

        app = create_app()
        with TestClient(app) as client:
            with patch(
                "app.api.routes.benchmark._get_service",
                return_value=BenchmarkService(settings=settings),
            ):
                response = client.get("/benchmark/results/xyz789")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "xyz789"

    def test_get_benchmark_result_not_found(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        app = create_app()
        with TestClient(app) as client:
            with patch(
                "app.api.routes.benchmark._get_service",
                return_value=BenchmarkService(settings=settings),
            ):
                response = client.get("/benchmark/results/doesnotexist")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestBenchmarkSchemas:
    """Validate Pydantic schema behaviour."""

    def test_run_request_defaults(self) -> None:
        req = BenchmarkRunRequest()
        assert PreprocessMode.ORIGINAL in req.modes
        assert req.fixture_dir is None
        assert req.max_pages is None

    def test_run_request_custom_modes(self) -> None:
        req = BenchmarkRunRequest(modes=["grayscale", "contrast"])
        assert PreprocessMode.GRAYSCALE in req.modes
        assert PreprocessMode.CONTRAST in req.modes

    def test_run_request_max_pages_positive(self) -> None:
        req = BenchmarkRunRequest(max_pages=5)
        assert req.max_pages == 5

    def test_run_request_max_pages_invalid(self) -> None:
        with pytest.raises(Exception):
            BenchmarkRunRequest(max_pages=0)

    def test_page_result_schema(self) -> None:
        r = PageBenchmarkResult(
            page_path="clean/page-001.png",
            mode=PreprocessMode.ORIGINAL,
            success=True,
            processing_time_ms=1234.5,
            attempts=1,
        )
        assert r.character_count == 0
        assert r.error is None

    def test_mode_summary_validity_rate_bounds(self) -> None:
        with pytest.raises(Exception):
            ModeSummary(
                mode=PreprocessMode.ORIGINAL,
                total_pages=1,
                success_count=1,
                failure_count=0,
                json_validity_rate=1.5,  # > 1.0 is invalid
                avg_processing_time_ms=100.0,
                total_processing_time_ms=100.0,
                avg_attempts=1.0,
                avg_character_count=0.0,
                avg_text_count=0.0,
                retry_rate=0.0,
            )
