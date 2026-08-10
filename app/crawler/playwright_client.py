"""Optional Playwright fetch for JS-heavy / client-rendered pages.

Hermes (and other hosts) often invoke tools inside a running asyncio loop.
Playwright's Sync API cannot run on that loop, so all browser work is executed
in a dedicated worker thread. Failures are logged with stage-level diagnostics
instead of silently returning None.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.settings import PlaywrightSettings
from app.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class PlaywrightFetchResult:
    html: str | None = None
    ok: bool = False
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class PlaywrightClient:
    def __init__(
        self,
        settings: PlaywrightSettings,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.settings = settings
        self.extra_headers = dict(extra_headers or {})
        self.last_result: PlaywrightFetchResult | None = None

    @staticmethod
    def is_available() -> bool:
        try:
            import playwright  # noqa: F401

            return True
        except ImportError:
            return False

    @staticmethod
    def browser_available() -> bool:
        """The package importing is not enough — the Chromium binary must exist."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        try:
            with sync_playwright() as p:
                return bool(p.chromium.executable_path)
        except Exception:  # noqa: BLE001
            return False

    def should_fetch(self, *, force_for_spa: bool = False) -> bool:
        """Use Playwright when explicitly enabled, or auto for SPA shells if installed."""
        if self.settings.enabled:
            return True
        return bool(force_for_spa and self.is_available())

    def fetch(self, url: str, *, force_for_spa: bool = False) -> str | None:
        result = self.fetch_with_diagnostics(url, force_for_spa=force_for_spa)
        self.last_result = result
        return result.html

    def fetch_with_diagnostics(
        self, url: str, *, force_for_spa: bool = False
    ) -> PlaywrightFetchResult:
        started = time.monotonic()
        diag: dict[str, Any] = {
            "url": url,
            "force_for_spa": force_for_spa,
            "enabled_flag": self.settings.enabled,
            "available": self.is_available(),
            "timeout_ms": self.settings.timeout_ms,
            "wait_until": self.settings.wait_until,
            "stages": [],
        }

        def _stage(name: str, **extra: Any) -> None:
            entry = {"stage": name, "t_ms": int((time.monotonic() - started) * 1000), **extra}
            diag["stages"].append(entry)
            logger.info("playwright_stage url=%s stage=%s extra=%s", url, name, extra)

        if not self.should_fetch(force_for_spa=force_for_spa):
            _stage("skipped", reason="not_enabled_and_not_forced_or_unavailable")
            result = PlaywrightFetchResult(error="playwright_skipped", diagnostics=diag)
            self.last_result = result
            return result

        try:
            import playwright  # noqa: F401
        except ImportError:
            _stage("import_failed")
            logger.warning(
                "Playwright requested but not installed. "
                "Install with: pip install 'seo-agent[playwright]' && playwright install chromium"
            )
            result = PlaywrightFetchResult(error="playwright_not_installed", diagnostics=diag)
            self.last_result = result
            return result

        # CRITICAL: Sync Playwright cannot run inside an asyncio loop (Hermes tool
        # executor). Always isolate browser work in a worker thread.
        _stage("thread_submit")
        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="seo-playwright"
            ) as pool:
                future = pool.submit(self._fetch_in_thread, url, diag)
                result = future.result(timeout=(self.settings.timeout_ms / 1000.0) + 30.0)
        except concurrent.futures.TimeoutError:
            _stage("thread_timeout")
            logger.error("Playwright thread timed out for %s", url)
            result = PlaywrightFetchResult(error="playwright_thread_timeout", diagnostics=diag)
        except Exception as exc:  # noqa: BLE001
            _stage("thread_error", error=str(exc))
            logger.exception("Playwright thread failed for %s", url)
            result = PlaywrightFetchResult(error=str(exc), diagnostics=diag)

        diag["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        diag["ok"] = result.ok
        diag["html_length"] = len(result.html or "")
        result.diagnostics = diag
        self.last_result = result
        if result.ok:
            logger.info(
                "playwright_ok url=%s html_len=%s elapsed_ms=%s",
                url,
                len(result.html or ""),
                diag["elapsed_ms"],
            )
        else:
            logger.warning(
                "playwright_failed url=%s error=%s stages=%s",
                url,
                result.error,
                diag.get("stages"),
            )
        return result

    def _fetch_in_thread(self, url: str, diag: dict[str, Any]) -> PlaywrightFetchResult:
        from playwright.sync_api import sync_playwright

        stages: list[dict[str, Any]] = diag.setdefault("stages", [])

        def stage(name: str, **extra: Any) -> None:
            stages.append({"stage": name, **extra})
            logger.info("playwright_thread_stage url=%s stage=%s %s", url, name, extra)

        try:
            with sync_playwright() as p:
                stage("launch_browser")
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )
                try:
                    stage("new_context")
                    context_kwargs: dict[str, Any] = {
                        "user_agent": _DEFAULT_UA,
                        "viewport": {"width": 1440, "height": 900},
                        "java_script_enabled": True,
                        "ignore_https_errors": True,
                    }
                    if self.extra_headers:
                        # Cookie / Authorization for GET navigation only — no form POST.
                        context_kwargs["extra_http_headers"] = dict(self.extra_headers)
                        stage("auth_headers_attached", names=sorted(self.extra_headers))
                    context = browser.new_context(**context_kwargs)
                    context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    )
                    page = context.new_page()

                    # Prefer a permissive first paint, then wait for app content.
                    wait_until = self.settings.wait_until or "domcontentloaded"
                    if wait_until == "networkidle":
                        # networkidle is flaky on SPAs with open websockets/analytics.
                        wait_until = "domcontentloaded"

                    stage("goto", wait_until=wait_until, timeout_ms=self.settings.timeout_ms)
                    page.goto(url, timeout=self.settings.timeout_ms, wait_until=wait_until)

                    stage("wait_content_selectors")
                    content_ready = False
                    for selector in (
                        "h1",
                        "main h1",
                        "#root h1",
                        "#app h1",
                        "#root a",
                        "#app a",
                        "main",
                        "[data-seo-ready]",
                    ):
                        try:
                            page.wait_for_selector(selector, timeout=8_000, state="visible")
                            stage("selector_ready", selector=selector)
                            content_ready = True
                            break
                        except Exception as sel_exc:  # noqa: BLE001
                            stage("selector_miss", selector=selector, error=str(sel_exc)[:160])

                    if not content_ready:
                        stage("fallback_networkidle_or_timeout")
                        try:
                            page.wait_for_load_state("networkidle", timeout=10_000)
                            stage("networkidle_ok")
                        except Exception as ni_exc:  # noqa: BLE001
                            stage("networkidle_miss", error=str(ni_exc)[:160])
                        page.wait_for_timeout(1500)
                    else:
                        # Allow late hydration after first meaningful node.
                        page.wait_for_timeout(800)

                    stage("page_content")
                    html = page.content()
                    text_len = len(page.inner_text("body") or "")
                    stage(
                        "captured",
                        html_length=len(html or ""),
                        body_text_length=text_len,
                    )
                    if not html or text_len < 40:
                        stage(
                            "thin_capture",
                            body_text_length=text_len,
                            html_length=len(html or ""),
                        )
                        # One soft reload retry for stubborn shells.
                        stage("retry_reload")
                        page.reload(wait_until="domcontentloaded", timeout=self.settings.timeout_ms)
                        try:
                            page.wait_for_selector("h1, main, #root a, #app a", timeout=10_000)
                        except Exception:  # noqa: BLE001
                            page.wait_for_timeout(2000)
                        html = page.content()
                        text_len = len(page.inner_text("body") or "")
                        stage(
                            "retry_captured",
                            html_length=len(html or ""),
                            body_text_length=text_len,
                        )

                    context.close()
                    if not html:
                        return PlaywrightFetchResult(
                            error="empty_html_after_render", diagnostics=diag
                        )
                    return PlaywrightFetchResult(html=html, ok=True, diagnostics=diag)
                finally:
                    stage("browser_close")
                    browser.close()
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            # A missing browser binary is the most common setup failure and is
            # indistinguishable from a render bug unless it is named explicitly.
            if "Executable doesn't exist" in message or "playwright install" in message:
                message = (
                    "Chromium browser binary is not installed. JS rendering cannot work "
                    "until you run: playwright install chromium"
                )
                stage("browser_binary_missing")
                diag["remediation"] = "playwright install chromium"
            stage("exception", error=message[:400])
            logger.exception("Playwright render exception for %s", url)
            return PlaywrightFetchResult(error=message, diagnostics=diag)
