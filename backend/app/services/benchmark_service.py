"""
Benchmark service — Phase 10.

Runs extraction pipeline across a fixture dataset using multiple preprocessing
modes (PRD §15). Collects timing, JSON validity rate, character/text counts,
and retry rates. Does NOT require real Ollama — uses ExtractionService so tests
can inject a mock OllamaService.

Benchmark modes (PRD §15.1):
  A: Full page → Gemma (original)
  B: Full page + preprocessing → Gemma (enhanced, contrast, grayscale, …)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.schemas.benchmark import (
    BenchmarkRunRequest,
    BenchmarkRunResult,
    BenchmarkStatus,
    ModeSummary,
    PageBenchmarkResult,
    PreprocessMode,
)
from app.services.extraction_service import ExtractionService
from app.services.image_service import ImageService, ImageServiceError
from app.services.ollama_service import OllamaError, OllamaService

logger = logging.getLogger(__name__)

# Image extensions accepted as fixture images
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class BenchmarkService:
    """Service that benchmarks extraction quality across preprocessing modes."""

    def __init__(
        self,
        settings: Settings | None = None,
        ollama_service: OllamaService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._ollama_service = ollama_service  # None → ExtractionService creates its own

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, request: BenchmarkRunRequest) -> BenchmarkRunResult:
        """Execute a benchmark run and return complete results.

        Args:
            request: Benchmark configuration (modes, fixture_dir, max_pages).

        Returns:
            BenchmarkRunResult with per-page results and per-mode summaries.
        """
        run_id = uuid.uuid4().hex[:12]
        started_at = datetime.now(timezone.utc)

        # Resolve fixture directory
        fixture_path = self._resolve_fixture_dir(request.fixture_dir)
        fixture_images = self._collect_fixtures(fixture_path, request.max_pages)

        logger.info(
            f"Benchmark run={run_id}: {len(fixture_images)} image(s), "
            f"modes={[m.value for m in request.modes]}, dir={fixture_path}"
        )

        page_results: list[PageBenchmarkResult] = []
        errors: list[str] = []

        for mode in request.modes:
            for img_path in fixture_images:
                result = await self._benchmark_single(img_path, mode, fixture_path)
                page_results.append(result)

        # Compute per-mode summaries
        mode_summaries = [
            self._compute_mode_summary(mode, page_results) for mode in request.modes
        ]

        recommended = self._pick_recommended_mode(mode_summaries)
        finished_at = datetime.now(timezone.utc)

        run_result = BenchmarkRunResult(
            run_id=run_id,
            status=BenchmarkStatus.DONE,
            started_at=started_at,
            finished_at=finished_at,
            modes_tested=request.modes,
            fixture_dir=str(fixture_path),
            total_fixtures=len(fixture_images),
            page_results=page_results,
            mode_summaries=mode_summaries,
            recommended_mode=recommended,
            errors=errors,
        )

        # Persist result to disk
        self._save_result(run_result)

        return run_result

    def load_results(self) -> list[dict[str, Any]]:
        """Load all persisted benchmark run result summaries from disk."""
        benchmark_dir = self._benchmark_dir()
        if not benchmark_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(benchmark_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except Exception as exc:
                logger.warning(f"Failed to load benchmark result {f}: {exc}")
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_fixture_dir(self, fixture_dir: str | None) -> Path:
        """Resolve fixture directory from request or default to tests/fixtures/."""
        if fixture_dir:
            path = Path(fixture_dir)
        else:
            # Default: project root / tests / fixtures
            path = self.settings.DATA_DIR.parent / "tests" / "fixtures"
        return path.resolve()

    def _collect_fixtures(self, fixture_path: Path, max_pages: int | None) -> list[Path]:
        """Collect image files from the fixture directory (non-recursive)."""
        if not fixture_path.exists():
            logger.warning(f"Fixture directory does not exist: {fixture_path}")
            return []

        images: list[Path] = sorted(
            p for p in fixture_path.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
        )

        # Also scan one level of subdirectories (e.g. clean/, difficult/)
        for sub in sorted(fixture_path.iterdir()):
            if sub.is_dir():
                images.extend(
                    sorted(
                        p for p in sub.iterdir()
                        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
                    )
                )

        if max_pages is not None:
            images = images[:max_pages]

        return images

    async def _benchmark_single(
        self,
        img_path: Path,
        mode: PreprocessMode,
        fixture_root: Path,
    ) -> PageBenchmarkResult:
        """Run extraction on one image with one preprocessing mode."""
        rel_path = str(img_path.relative_to(fixture_root)) if img_path.is_relative_to(fixture_root) else img_path.name
        t0 = time.perf_counter()

        try:
            img = ImageService.load_image(img_path)
        except ImageServiceError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return PageBenchmarkResult(
                page_path=rel_path,
                mode=mode,
                success=False,
                processing_time_ms=elapsed,
                attempts=1,
                error=f"Image load error: {exc}",
            )

        extraction_service = ExtractionService(
            settings=self.settings,
            ollama_service=self._ollama_service,
        )

        try:
            result = await extraction_service.extract_page(
                image_input=img,
                page_num=1,
                preprocess_mode=mode.value,
                max_retries=2,  # 3 total attempts per PRD §13.1
            )
            elapsed = (time.perf_counter() - t0) * 1000

            raw_size = len(json.dumps(result.raw_response).encode())

            return PageBenchmarkResult(
                page_path=rel_path,
                mode=mode,
                success=True,
                processing_time_ms=elapsed,
                attempts=result.attempts,
                character_count=len(result.page_context.characters),
                text_count=len(result.page_context.texts),
                has_scene=result.page_context.scene is not None,
                error=None,
                raw_response_size=raw_size,
            )

        except OllamaError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.warning(f"Benchmark {mode.value}/{rel_path} OllamaError: {exc}")
            return PageBenchmarkResult(
                page_path=rel_path,
                mode=mode,
                success=False,
                processing_time_ms=elapsed,
                attempts=3,
                error=f"OllamaError: {exc}",
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.warning(f"Benchmark {mode.value}/{rel_path} failed: {exc}")
            return PageBenchmarkResult(
                page_path=rel_path,
                mode=mode,
                success=False,
                processing_time_ms=elapsed,
                attempts=3,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_mode_summary(
        mode: PreprocessMode,
        all_results: list[PageBenchmarkResult],
    ) -> ModeSummary:
        """Aggregate benchmark results for one preprocessing mode."""
        results = [r for r in all_results if r.mode == mode]
        total = len(results)
        if total == 0:
            return ModeSummary(
                mode=mode,
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

        success_count = sum(1 for r in results if r.success)
        failure_count = total - success_count
        validity_rate = success_count / total
        total_ms = sum(r.processing_time_ms for r in results)
        avg_ms = total_ms / total
        avg_attempts = sum(r.attempts for r in results) / total
        retry_count = sum(1 for r in results if r.attempts > 1)
        retry_rate = retry_count / total
        avg_chars = sum(r.character_count for r in results) / total
        avg_texts = sum(r.text_count for r in results) / total

        return ModeSummary(
            mode=mode,
            total_pages=total,
            success_count=success_count,
            failure_count=failure_count,
            json_validity_rate=round(validity_rate, 4),
            avg_processing_time_ms=round(avg_ms, 2),
            total_processing_time_ms=round(total_ms, 2),
            avg_attempts=round(avg_attempts, 3),
            avg_character_count=round(avg_chars, 2),
            avg_text_count=round(avg_texts, 2),
            retry_rate=round(retry_rate, 4),
        )

    @staticmethod
    def _pick_recommended_mode(
        summaries: list[ModeSummary],
    ) -> PreprocessMode | None:
        """Pick the mode with the best validity rate; break ties by speed.

        Returns None when no pages were tested.
        """
        valid = [s for s in summaries if s.total_pages > 0]
        if not valid:
            return None

        # Primary: highest validity rate; secondary: lowest avg processing time
        best = max(
            valid,
            key=lambda s: (s.json_validity_rate, -s.avg_processing_time_ms),
        )
        return best.mode

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _benchmark_dir(self) -> Path:
        """Return the benchmark results directory, creating it if necessary."""
        bdir = self.settings.DATA_DIR / "benchmarks"
        bdir.mkdir(parents=True, exist_ok=True)
        return bdir

    def _save_result(self, result: BenchmarkRunResult) -> None:
        """Persist a benchmark run result as JSON."""
        out_path = self._benchmark_dir() / f"benchmark-{result.run_id}.json"
        try:
            out_path.write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            logger.info(f"Benchmark result saved: {out_path}")
        except Exception as exc:
            logger.error(f"Failed to save benchmark result: {exc}")
