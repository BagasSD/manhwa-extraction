"""
Benchmark schemas — Phase 10.

Defines request/response models for the benchmarking system that evaluates
extraction accuracy and timing across preprocessing modes (PRD §15).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PreprocessMode(str, Enum):
    """Supported preprocessing strategies (PRD §5.1)."""

    ORIGINAL = "original"
    UPSCALE = "upscale"
    ENHANCED = "enhanced"
    GRAYSCALE = "grayscale"
    CONTRAST = "contrast"
    SHARPEN = "sharpen"


class BenchmarkStatus(str, Enum):
    """Status of a benchmark run."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class BenchmarkRunRequest(BaseModel):
    """Request body for POST /benchmark/run."""

    modes: list[PreprocessMode] = Field(
        default_factory=lambda: [
            PreprocessMode.ORIGINAL,
            PreprocessMode.ENHANCED,
            PreprocessMode.GRAYSCALE,
        ],
        description="Preprocessing modes to benchmark (defaults: original, enhanced, grayscale).",
    )
    fixture_dir: str | None = Field(
        default=None,
        description=(
            "Path to fixture directory. Defaults to tests/fixtures/ relative to project root."
        ),
    )
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of fixture images to run (None = all).",
    )


# ---------------------------------------------------------------------------
# Per-page result
# ---------------------------------------------------------------------------


class PageBenchmarkResult(BaseModel):
    """Extraction result for a single fixture page under one preprocessing mode."""

    page_path: str = Field(description="Relative path of the fixture image file.")
    mode: PreprocessMode
    success: bool = Field(description="True if JSON was valid and Pydantic schema passed.")
    processing_time_ms: float = Field(ge=0.0)
    attempts: int = Field(ge=1)
    character_count: int = Field(ge=0, default=0)
    text_count: int = Field(ge=0, default=0)
    has_scene: bool = False
    error: str | None = None
    raw_response_size: int = Field(
        ge=0,
        default=0,
        description="Raw response JSON byte size.",
    )


# ---------------------------------------------------------------------------
# Per-mode summary
# ---------------------------------------------------------------------------


class ModeSummary(BaseModel):
    """Aggregated statistics for one preprocessing mode across all fixture pages."""

    mode: PreprocessMode
    total_pages: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    json_validity_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of pages that returned valid JSON matching the schema.",
    )
    avg_processing_time_ms: float = Field(ge=0.0)
    total_processing_time_ms: float = Field(ge=0.0)
    avg_attempts: float = Field(ge=1.0)
    avg_character_count: float = Field(ge=0.0)
    avg_text_count: float = Field(ge=0.0)
    retry_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of pages that needed more than one attempt.",
    )


# ---------------------------------------------------------------------------
# Full benchmark run
# ---------------------------------------------------------------------------


class BenchmarkRunResult(BaseModel):
    """Complete result of a benchmark run across all modes and fixture pages."""

    run_id: str
    status: BenchmarkStatus = BenchmarkStatus.DONE
    started_at: datetime
    finished_at: datetime | None = None
    modes_tested: list[PreprocessMode]
    fixture_dir: str
    total_fixtures: int = Field(ge=0)
    page_results: list[PageBenchmarkResult] = Field(default_factory=list)
    mode_summaries: list[ModeSummary] = Field(default_factory=list)
    recommended_mode: PreprocessMode | None = Field(
        default=None,
        description="Mode with the best combination of validity rate and speed.",
    )
    errors: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Any additional metadata produced during the run.",
    )
