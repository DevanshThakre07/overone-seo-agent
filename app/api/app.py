from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import __version__
from app.api.auth import api_key_configured, enforce_api_key
from app.api.routes import (
    audit,
    auth_google,
    competitive,
    dashboard,
    ga4,
    history,
    keywords,
    login_wall,
    optimize,
    pagespeed,
    report,
    schedules,
    share,
    trends,
)
from app.api.dependencies import get_job_runner
from app.config.settings import get_settings
from app.logging import setup_logging
from app.services.scheduler_runner import start_scheduler, stop_scheduler


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            await enforce_api_key(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=dict(exc.headers or {}),
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(_application: FastAPI):
    runner = get_job_runner()
    if hasattr(runner, "start"):
        runner.start()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        if hasattr(runner, "stop"):
            runner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    application = FastAPI(
        title="AI SEO Agent API",
        description=(
            "Standalone SEO engine HTTP API. "
            "Hermes can call these endpoints as thin tool adapters. "
            "Customers connect Google via /auth/google/start for Search Console data. "
            "PageSpeed Insights adds Core Web Vitals when GOOGLE_PAGESPEED_API_KEY is set. "
            "Keyword research (volume/CPC) uses DataForSEO when KEYWORD_API_* is set. "
            "Competitive SEO (SERP / rank / backlinks) is opt-in via /serp, /rank, "
            "/backlinks or audit flags include_serp / include_backlinks. "
            "Phase 3: /trends, /schedules, /dashboard, /share. "
            "Phase 4A: durable /jobs queue (SQLite default; Postgres via SEO_DATABASE_URL). "
            "GA4: /ga4/properties + /ga4/report (same Connect Google account_id; re-consent for Analytics). "
            "OAuth Production: GET /auth/google/production + /legal/privacy; "
            "set GSC_OAUTH_PUBLISHING_STATUS=production after Google Cloud Publish. "
            "PDF: GET /report/{id}?format=pdf or /share/{token}?format=pdf "
            "(pip install 'seo-agent[pdf]'). "
            "When SEO_API_KEY is set, protected routes require Bearer or X-API-Key. "
            "Authenticated crawl uses in-memory cookies on GET/HEAD only; "
            "GET /crawl/login-wall dry-runs login detection without credentials."
        ),
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(ApiKeyMiddleware)

    @application.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "version": __version__,
            "api_auth_required": api_key_configured(),
        }

    application.include_router(audit.router)
    application.include_router(optimize.router)
    application.include_router(report.router)
    application.include_router(history.router)
    application.include_router(auth_google.router)
    application.include_router(ga4.router)
    application.include_router(pagespeed.router)
    application.include_router(keywords.router)
    application.include_router(competitive.router)
    application.include_router(login_wall.router)
    application.include_router(trends.router)
    application.include_router(schedules.router)
    application.include_router(dashboard.router)
    application.include_router(share.router)
    return application


app = create_app()


def run() -> None:
    """CLI entry: seo-api"""
    uvicorn.run("app.api.app:app", host="0.0.0.0", port=8000, reload=False)
