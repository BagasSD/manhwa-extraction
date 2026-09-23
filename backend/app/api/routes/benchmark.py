"""
Benchmark API routes — Phase 10.

POST /benchmark/run    → launch benchmark, returns BenchmarkRunResult
GET  /benchmark/results → list all saved benchmark run summaries
GET  /benchmark/results/{run_id} → retrieve a specific benchmark run
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas.benchmark import BenchmarkRunRequest, BenchmarkRunResult
from app.services.benchmark_service import BenchmarkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _get_service() -> BenchmarkService:
    return BenchmarkService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=BenchmarkRunResult, status_code=200)
async def run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResult:
    """
    Run extraction benchmarks across fixture images for each requested mode.

    Returns aggregate metrics:
    - JSON validity rate per mode
    - Average processing time per mode
    - Retry rate per mode
    - Recommended preprocessing mode
    """
    service = _get_service()
    try:
        result = await service.run(request)
        return result
    except Exception as exc:
        logger.exception("Benchmark run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/results", response_model=list[dict[str, Any]])
def list_benchmark_results() -> list[dict[str, Any]]:
    """List all saved benchmark run results (most recent first)."""
    service = _get_service()
    return service.load_results()


@router.get("/results/{run_id}", response_model=dict[str, Any])
def get_benchmark_result(run_id: str) -> dict[str, Any]:
    """Retrieve a specific benchmark run result by run_id."""
    service = _get_service()
    all_results = service.load_results()
    for r in all_results:
        if r.get("run_id") == run_id:
            return r
    raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
