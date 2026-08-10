"""Connect Google (OAuth) + Search Console API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.dependencies import get_gsc_service
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.google.oauth_production import production_checklist
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
        False,
        description=(
            "If true, 302 straight to Google. Default false shows a page with a "
            "single Continue button (avoids broken copy-paste / mangled redirects)."
        ),
    ),
    as_json: bool = Query(
        False,
        description="Return JSON {authorization_url,...} instead of HTML.",
    ),
    include_analytics: bool = Query(
        True,
        description="Request analytics.readonly (GA4). Set false for GSC-only connect.",
    ),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        started = gsc.start_connect(
            account_id.strip() or "default",
            include_analytics=include_analytics,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if as_json:
        return started
    if redirect:
        return RedirectResponse(url=started["authorization_url"], status_code=302)

    url = started["authorization_url"]
    aid = started["account_id"]
    publishing = production_checklist(gsc.settings.gsc)
    pub = publishing["publishing_status"]
    analytics_note = (
        "This will ask for Search Console + Google Analytics."
        if include_analytics
        else "This will ask for Search Console only (no GA4)."
    )
    if pub == "production":
        account_note = (
            "Sign in with the Google account that owns the customer's Search Console "
            "/ GA4 property (not necessarily the Cloud Console owner)."
        )
        mode_banner = ""
    else:
        account_note = (
            "OAuth consent is still in <strong>Testing</strong>. Only Google emails "
            "listed under Cloud Console → OAuth consent screen → <strong>Test users</strong> "
            "can continue. Real customers need Production — see "
            "<code>/auth/google/production</code>."
        )
        mode_banner = (
            '<p class="banner">Publishing status: <strong>Testing</strong> '
            "(set <code>GSC_OAUTH_PUBLISHING_STATUS=production</code> after you Publish "
            "in Google Cloud).</p>"
        )
    html = f"""<!doctype html>
<html><head><title>Connect Google</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 36rem; margin: 3rem auto; padding: 0 1rem; line-height: 1.45; }}
  a.btn {{
    display: inline-block; margin-top: 1rem; padding: 0.85rem 1.35rem;
    background: #1a73e8; color: #fff; text-decoration: none; border-radius: 6px;
    font-weight: 600;
  }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.35rem; border-radius: 4px; }}
  .warn {{ color: #5f6368; font-size: 0.95rem; margin-top: 1.25rem; }}
  .banner {{
    background: #fef7e0; border: 1px solid #f9ab00; padding: 0.75rem 1rem;
    border-radius: 6px; font-size: 0.95rem;
  }}
</style></head>
<body>
  <h1>Connect Google</h1>
  {mode_banner}
  <p>Account id: <code>{aid}</code></p>
  <p>{analytics_note}</p>
  <p>{account_note}</p>
  <p><a class="btn" href="{url}">Continue to Google</a></p>
  <p class="warn">
    On Google: choose the account → click <strong>Continue / Allow</strong>.
    Do <em>not</em> open Help / Learn more / Report an app — that is a different page.
  </p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/auth/callback")
def google_connect_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    if error:
        publishing = production_checklist(gsc.settings.gsc)
        detail = error_description or error
        if error == "access_denied" and publishing["publishing_status"] != "production":
            html = f"""<!doctype html>
<html><head><title>Google connect blocked</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; line-height: 1.45; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.35rem; border-radius: 4px; }}
</style></head>
<body>
  <h1>Could not connect Google</h1>
  <p>Google returned <code>{error}</code>: {detail}</p>
  <p>While the OAuth app is in <strong>Testing</strong>, only emails listed as
  <strong>Test users</strong> can approve Connect Google.</p>
  <ol>
    <li>Google Cloud → APIs &amp; Services → OAuth consent screen → Test users</li>
    <li>Add the Google email you are signing in with</li>
    <li>Retry <code>/auth/google/start?account_id=...</code></li>
  </ol>
  <p>For real customers: publish to Production — checklist at
  <code>GET /auth/google/production</code>.</p>
</body></html>"""
            return HTMLResponse(content=html, status_code=400)
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {detail}")
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
  <h1>Google connected</h1>
  <p>Account: <code>{result.get("account_id")}</code></p>
  <p>Google email: <code>{result.get("email") or "unknown"}</code></p>
  <p>Analytics scope: <code>{"yes" if result.get("has_analytics_scope") else "no — reconnect to grant"}</code></p>
  <p>Next:</p>
  <ol>
    <li>Search Console sites: <code>GET /gsc/sites?account_id={result.get("account_id")}</code></li>
    <li>Search Console performance:
      <code>GET /gsc/performance?account_id={result.get("account_id")}&amp;site_url=...</code>
    </li>
    <li>GA4 properties: <code>GET /ga4/properties?account_id={result.get("account_id")}</code></li>
    <li>GA4 report:
      <code>GET /ga4/report?account_id={result.get("account_id")}&amp;property_id=...</code>
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


@router.get("/auth/google/production")
def google_oauth_production(
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    """Owner checklist: Testing → Production publish + verification."""
    return gsc.production_status()


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy_policy(gsc: GoogleSearchConsoleService = Depends(get_gsc_service)):
    """Public privacy policy stub for Google OAuth consent screen.

    Deploy seo-api on HTTPS and paste this URL into the consent screen
    (or set GSC_PRIVACY_POLICY_URL to a custom page you host).
    """
    publishing = production_checklist(gsc.settings.gsc)
    custom = publishing.get("privacy_policy_url")
    custom_note = (
        f"<p>Configured public URL: <a href=\"{custom}\">{custom}</a></p>"
        if custom
        else "<p>Tip: set <code>GSC_PRIVACY_POLICY_URL</code> to the HTTPS URL you "
        "paste into Google Cloud (this path works when seo-api is publicly reachable).</p>"
    )
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>Privacy Policy — SEO Agent</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 42rem; margin: 2.5rem auto; padding: 0 1.25rem; line-height: 1.55; color: #202124; }}
  h1 {{ font-size: 1.6rem; }}
  h2 {{ font-size: 1.15rem; margin-top: 1.75rem; }}
  code {{ background: #f1f3f4; padding: 0.1rem 0.35rem; border-radius: 4px; }}
</style></head>
<body>
  <h1>Privacy Policy</h1>
  <p>Last updated: 2026-08-08</p>
  {custom_note}
  <p>
    SEO Agent (“we”, “the product”) helps website owners audit technical SEO and
    optionally connect Google Search Console and Google Analytics (GA4) to enrich reports.
  </p>
  <h2>Google data we access</h2>
  <ul>
    <li><strong>Search Console</strong> (readonly): verified site list and search
      performance (queries, pages, clicks, impressions, CTR, position).</li>
    <li><strong>Google Analytics</strong> (readonly, when granted): GA4 property list
      and aggregate traffic metrics (sessions, users, views, top pages).</li>
    <li><strong>Account email</strong> (OpenID): to label the connected account.</li>
  </ul>
  <h2>How we use it</h2>
  <p>
    Data is used only to run SEO audits, dashboards, and reports for the customer who
    connected their Google account. We do not sell Google data. We do not use it for
    advertising.
  </p>
  <h2>Storage</h2>
  <p>
    OAuth tokens are stored per customer <code>account_id</code> in the product’s
    token database so the connection can refresh without asking Google every time.
    Customers (or operators) can disconnect via
    <code>POST /auth/google/disconnect</code>, which deletes stored tokens for that account.
  </p>
  <h2>Sharing</h2>
  <p>
    We do not share Google-connected data with third parties except as needed to
    operate the product infrastructure you deploy (e.g. your own database host) or
    when required by law.
  </p>
  <h2>Contact</h2>
  <p>
    Replace this contact with your support email on the Google OAuth consent screen
    and in any custom privacy page you publish.
  </p>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/auth/google/disconnect")
def google_disconnect(
    account_id: str = Query("default"),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    return gsc.disconnect(account_id.strip() or "default")


@router.get("/gsc/sites")
def gsc_sites(
    account_id: str = Query(...),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        return gsc.list_sites(account_id.strip())
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SearchConsoleError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/gsc/performance")
def gsc_performance(
    account_id: str = Query(...),
    site_url: str = Query(...),
    days: int = Query(28, ge=1, le=90),
    top_n: int = Query(20, ge=1, le=50),
    gsc: GoogleSearchConsoleService = Depends(get_gsc_service),
):
    try:
        return gsc.performance(
            account_id.strip(),
            site_url.strip(),
            days=days,
            top_n=top_n,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SearchConsoleError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
