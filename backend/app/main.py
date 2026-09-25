from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import benchmark, chapters, export, extraction, health, pages, panels
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directories exist on startup so persistence and exports
    # can rely on them being present.
    settings = get_settings()
    for path in (settings.CHAPTERS_DIR, settings.RESULTS_DIR, settings.EXPORTS_DIR, settings.EXTRACTED_IMAGE_DIR):
        path.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chapters.router)
    app.include_router(pages.router)
    app.include_router(extraction.router)
    app.include_router(export.router)
    app.include_router(benchmark.router)
    app.include_router(panels.router)

    return app


app = create_app()
