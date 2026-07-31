from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from app import __version__
from app.api.routes import audit, history, optimize, report
from app.config.settings import get_settings
from app.logging import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    application = FastAPI(
        title="AI SEO Agent API",
        description=(
            "Standalone SEO engine HTTP API. "
            "Hermes can call these endpoints as thin tool adapters."
        ),
        version=__version__,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    application.include_router(audit.router)
    application.include_router(optimize.router)
    application.include_router(report.router)
    application.include_router(history.router)
    return application


app = create_app()


def run() -> None:
    """CLI entry: seo-api"""
    uvicorn.run("app.api.app:app", host="0.0.0.0", port=8000, reload=False)
