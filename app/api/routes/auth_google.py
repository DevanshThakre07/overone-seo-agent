"""Connect Google (OAuth) + Search Console API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.dependencies import get_gsc_service
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.google.search_console import SearchConsoleError
from app.integrations.google.service import GoogleSearchConsoleService
from app.logging import get_logger, log_event

router = APIRouter(tags=["google-search-console"])
logger = get_logger(__name__)


@router.get("/auth/google/start")
def google_connect_start(
    account_id: str = Query(
        "default",
        description=(
            "Your customer's stable id in your product (email, tenant id, etc.). "
            "Each customer gets their own Google connection."
        ),
    ),
    redirect: bool = Query(
        True,
        description="If true, redirect the browser to Google. If false, return JSON with the URL.",
    ),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        started = gsc.start_connect(account_id.strip() or "default")
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if redirect:
        return RedirectResponse(url=started["authorization_url"], status_code=302)
    return started


@router.get("/auth/callback")
def google_connect_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        result = gsc.complete_connect(code=code, state=state)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_event(logger, "gsc_oauth_callback_ok", account_id=result.get("account_id"))
    html = f"""<!doctype html>
<html><head><title>Google connected</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.35rem; border-radius: 4px; }}
</style></head>
<body>
  <h1>Google Search Console connected</h1>
  <p>Account: <code>{result.get("account_id")}</code></p>
  <p>Google email: <code>{result.get("email") or "unknown"}</code></p>
  <p>Next:</p>
  <ol>
    <li>List properties: <code>GET /gsc/sites?account_id={result.get("account_id")}</code></li>
    <li>Pull performance:
      <code>GET /gsc/performance?account_id={result.get("account_id")}&amp;site_url=...</code>
    </li>
  </ol>
  <p>You can close this tab and return to the SEO agent.</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/auth/google/status")
def google_connect_status(
    account_id: str = Query("default"),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    return gsc.status(account_id.strip() or "default")


@router.post("/auth/google/disconnect")
def google_disconnect(
    account_id: str = Query("default"),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    return gsc.disconnect(account_id.strip() or "default")


@router.get("/gsc/sites")
def gsc_sites(
    account_id: str = Query("default"),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        return gsc.list_sites(account_id.strip() or "default")
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SearchConsoleError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/gsc/performance")
def gsc_performance(
    site_url: str = Query(..., description="Exact Search Console property URL or sc-domain:..."),
    account_id: str = Query("default"),
    days: int = Query(28, ge=1, le=90),
    top_n: int = Query(20, ge=1, le=100),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        return gsc.performance(
            account_id.strip() or "default",
            site_url,
            days=days,
            top_n=top_n,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SearchConsoleError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
