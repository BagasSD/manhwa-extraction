"""
Benchmark service — Phase 10.

Runs extraction pipeline across a fixture dataset using multiple preprocessing
modes (PRD §15). Collects timing, JSON validity rate, character/text counts,
and retry rates. Does NOT require real Ollama — uses ExtractionService so tests
can inject a mock OllamaService.

Benchmark modes (PRD §15.1):
  A: Full page → Gemma (original)
  B: Full page + preprocessing → Gemma (enhanced, contrast, grayscale, …)
  C: Crop + upscale → Gemma (tiled)

Text recall: an `expected.json` next to the fixtures (in the fixture root or a
category subfolder) lists the ground-truth texts per image, e.g.
  {"page-001.png": {"texts": ["Don't leave!"]}}
Each run then reports how many of those texts were captured, so a prompt or
preprocessing change can be compared before/after on the same fixed set.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from difflib import SequenceMatcher
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
EXPECTED_TEXTS_FILENAME = "expected.json"
# Minimum similarity for an extracted text to count as a ground-truth match
# (tolerates small OCR slips such as a missing apostrophe).
_TEXT_MATCH_RATIO = 0.8
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


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
        expected_texts = self._load_expected_texts(fixture_path)

        logger.info(
            f"Benchmark run={run_id}: {len(fixture_images)} image(s), "
            f"modes={[m.value for m in request.modes]}, dir={fixture_path}"
        )

        page_results: list[PageBenchmarkResult] = []
        errors: list[str] = []

        for mode in request.modes:
            for img_path in fixture_images:
                result = await self._benchmark_single(img_path, mode, fixture_path, expected_texts)
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

    @staticmethod
    def _load_expected_texts(fixture_path: Path) -> dict[str, list[str]]:
        """Read ground-truth texts from expected.json in the root and category subfolders.

        Keys in the result are image paths relative to `fixture_path` (POSIX style).
        """
        manifests = [fixture_path / EXPECTED_TEXTS_FILENAME]
        if fixture_path.is_dir():
            manifests += [sub / EXPECTED_TEXTS_FILENAME for sub in sorted(fixture_path.iterdir()) if sub.is_dir()]

        expected: dict[str, list[str]] = {}
        for manifest in manifests:
            if not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Ignoring unreadable {manifest}: {exc}")
                continue
            prefix = manifest.parent.relative_to(fixture_path).as_posix()
            for name, entry in data.items():
                texts = entry.get("texts") if isinstance(entry, dict) else None
                if isinstance(texts, list):
                    key = name if prefix == "." else f"{prefix}/{name}"
                    expected[key] = [str(t) for t in texts]
        return expected

    @staticmethod
    def _normalize_text(text: str) -> str:
        return _NON_WORD_RE.sub(" ", text.casefold()).strip()

    @classmethod
    def count_matched_texts(cls, expected: list[str], extracted: list[str]) -> int:
        """Count ground-truth texts present in the extraction (fuzzy, order-independent)."""
        extracted_norm = [cls._normalize_text(t) for t in extracted if t.strip()]
        joined = " ".join(extracted_norm)
        matched = 0
        for text in expected:
            target = cls._normalize_text(text)
            if not target:
                continue
            if target in joined or any(
                SequenceMatcher(None, target, cand).ratio() >= _TEXT_MATCH_RATIO for cand in extracted_norm
            ):
                matched += 1
        return matched

    @classmethod
    def _recall_fields(cls, expected: list[str] | None, extracted: list[str]) -> dict[str, Any]:
        """Ground-truth comparison fields for a PageBenchmarkResult."""
        if expected is None:
            return {}
        matched = cls.count_matched_texts(expected, extracted)
        return {
            "expected_text_count": len(expected),
            "matched_text_count": matched,
            "text_recall": matched / len(expected) if expected else None,
        }

    async def _benchmark_single(
        self,
        img_path: Path,
        mode: PreprocessMode,
        fixture_root: Path,
        expected_texts: dict[str, list[str]] | None = None,
    ) -> PageBenchmarkResult:
        """Run extraction on one image with one preprocessing mode."""
        rel_path = img_path.relative_to(fixture_root).as_posix() if img_path.is_relative_to(fixture_root) else img_path.name
        expected = (expected_texts or {}).get(rel_path)
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
                flagged=bool(result.page_context.review_flags),
                **self._recall_fields(expected, [t.text for t in result.page_context.texts]),
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
                **self._recall_fields(expected, []),
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
                **self._recall_fields(expected, []),
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
        recalls = [r.text_recall for r in results if r.text_recall is not None]
        avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else None
        missed_text_pages = sum(1 for r in results if r.expected_text_count and r.text_count == 0)
        hallucinated_text_pages = sum(
            1 for r in results if r.success and r.expected_text_count == 0 and r.text_count > 0
        )
        flagged_pages = sum(1 for r in results if r.flagged)

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
            avg_text_recall=avg_recall,
            missed_text_pages=missed_text_pages,
            hallucinated_text_pages=hallucinated_text_pages,
            flagged_pages=flagged_pages,
        )

    @staticmethod
    def _pick_recommended_mode(
        summaries: list[ModeSummary],
    ) -> PreprocessMode | None:
        """Pick the mode that captures the most text, then the best validity rate, then speed.

        Text recall only counts when the fixtures have ground truth. Returns
        None when no pages were tested.
        """
        valid = [s for s in summaries if s.total_pages > 0]
        if not valid:
            return None

        best = max(
            valid,
            key=lambda s: (
                s.avg_text_recall if s.avg_text_recall is not None else -1.0,
                s.json_validity_rate,
                -s.avg_processing_time_ms,
            ),
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
