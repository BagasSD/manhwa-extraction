from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """Basic liveness check used by Phase 0 acceptance criteria."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }
