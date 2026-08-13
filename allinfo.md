# SEO Agent — Complete Contributor Guide (`allinfo`)

In-depth reference for **this repository only**: what the agent is, how every major piece works, and how to run and extend it.  
Audience: **contributors and integrators** building against the Dashboard + HTTP API.

Related shorter docs:

| Doc | Role |
|-----|------|
| [`README.md`](README.md) | Quick start |
| [`docs/understand.md`](docs/understand.md) | Dashboard beginner labels |
| [`docs/HOSTING.md`](docs/HOSTING.md) | Docker / HTTPS deploy |
| [`docs/GOOGLE_SEARCH_CONSOLE.md`](docs/GOOGLE_SEARCH_CONSOLE.md) | Connect Google / GSC detail |
| [`docs/planning.md`](docs/planning.md) | Living roadmap / Plan Perfect |

---

## 1. What this agent is

**SEO Agent** is a standalone, modular **SEO engine**:

1. **Crawl** a site (HTTP + optional Playwright for JS/SPA).  
2. **Extract** on-page SEO fields (title, meta, headings, links, images, schema, …).  
3. **Analyze** via independent plugin analyzers.  
4. **Score** issues and build **evidence-backed recommendations**.  
5. Optionally **enrich** with Google Search Console, Google Analytics 4, PageSpeed Insights, and DataForSEO (keywords / SERP / rank / backlinks).  
6. Persist audits, compare history, schedule re-runs, share reports, and expose everything through **FastAPI** + a **Dashboard UI**.

It is designed to run as:

- A **local / hosted API** (`seo-api`) with Dashboard at `/dashboard/ui`
- A **CLI** (`seo-audit`, `seo-optimize`, `seo-report`, …)
- An **embeddable backend feature** inside a larger product (call the same HTTP API)

**Important product rule:** optimize / recommendations are **advice only**. The agent does **not** edit the customer’s live site or CMS.

---

## 2. High-level architecture

```text
  Browser Dashboard  ──┐
  CLI (seo-audit …)  ──┼──►  tools/  (thin wrappers)
  HTTP / OpenAPI     ──┘         │
                                 ▼
                           services/
                     (SeoService, CrawlerService,
                      OptimizerService, MemoryService,
                      dashboard_service, alerts, …)
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
          crawler/          extractor/         analyzers/
          (HTTP +           (HTML →            (plugins →
           Playwright)       PageExtraction)    Issue[])
                                 │
                                 ▼
                    repositories / SQLite or Postgres
                    (audits, jobs, schedules, shares,
                     rank_snapshots, gsc tokens, …)
                                 │
                                 ▼
                    reports/ (Markdown, JSON, PDF)
                    static/dashboard.html (UI)
```

**Core orchestration:** `app/services/seo_service.py` → `SeoService.run_audit()`.

**HTTP entry:** `app/api/app.py` → FastAPI app, API-key middleware, routers, background job runner + schedule loop on lifespan.

**UI entry:** `GET /dashboard/ui` serves `app/static/dashboard.html` (single-page dashboard that calls the same API).

---

## 3. Repository map (what lives where)

| Path | Purpose |
|------|---------|
| `app/crawler/` | Fetch pages, robots respect, optional Playwright, optional cookie/header auth |
| `app/extractor/` | BeautifulSoup/lxml extraction → `PageExtraction` |
| `app/analyzers/` | One plugin per SEO check + scorer + recommendations + rendering guardrails |
| `app/services/` | Business logic (audit, crawl, optimize, dashboard assembly, alerts, schedules) |
| `app/api/` | FastAPI routes, auth middleware, durable jobs |
| `app/tools/` | Named Python callables used by CLI and internal callers |
| `app/integrations/` | Google (GSC/GA4/PageSpeed), DataForSEO (keywords/competitive) |
| `app/optimizer/` | LLM-backed page optimize + keyword placement helpers |
| `app/reports/` | Markdown / PDF + `signal_trust` (honest “not run / error” stubs) |
| `app/repositories/` | Persistence adapters |
| `app/models/` | Pydantic models (`PageExtraction`, `SiteAudit`, issues, …) |
| `app/static/dashboard.html` | Contributor / operator dashboard |
| `config/default.yaml` | Default crawl / scoring / feature knobs |
| `.env` / `.env.example` | Secrets & env overrides (**.env is never committed**) |
| `secrets/` | OAuth client JSON (**gitignored**) |
| `data/` | Local SQLite DBs (**gitignored** except `.gitkeep`) |
| `tests/` | Unit + fixture golden pages for recommendation accuracy |
| `Dockerfile` / `docker-compose.yml` | Runnable `seo-api` image |
| `docs/` | Hosting, GSC, planning, beginner dashboard guide |

---

## 4. End-to-end: how an audit works

### 4.1 Trigger

Any of:

- Dashboard **Run audit**
- `POST /audit`
- CLI `seo-audit https://example.com …`
- A due **schedule** (enqueues the same job path)

Optional `background=true` on `POST /audit` → durable job → poll `GET /jobs/{job_id}`.

### 4.2 Pipeline inside `SeoService.run_audit`

1. **Options** — max pages/depth, save/compare, GSC/GA4 account ids, PageSpeed on/off, SERP/backlinks opt-in, auth crawl flags, optimize flags.  
2. **Login-wall probe** — dry-run detection of gated pages (no credentials required for the probe).  
3. **Crawl** — BFS/same-host crawl up to limits; SPA/JS shells can auto-trigger Playwright when installed.  
4. **Extract** — each HTML response → `PageExtraction` (title, meta, Hn, links, images, canonical, JSON-LD, word count, …).  
5. **Rendering guardrails** — if the page looks like an unrendered JS shell, suppress false “missing H1” style findings and require JS rendering first.  
6. **Analyzers** — `AnalyzerRegistry.run_all()`; one failure does not abort the whole audit.  
7. **Aggregate + score** — severity counts + prevalence-aware score (see `config/default.yaml` scoring).  
8. **Prescriptive recommendations** — concrete title/meta/H1 rewrite candidates with **evidence** (`url`, `field`, `current_value`, `suggested_value`).  
9. **Enrichment (optional)**  
   - PageSpeed on seed URL if `GOOGLE_PAGESPEED_API_KEY` set  
   - GSC performance / opportunities if `gsc_account_id` connected  
   - GA4 report if `include_ga4` + property preference  
   - SERP / backlinks only when explicitly opted in (paid DataForSEO)  
10. **Merge GSC opportunities** into recommendations when GSC status is `ok`.  
11. **Persist** if `save` / `compare` / API path requires history.  
12. **Alerts** (schedules/compare) if webhook configured and score drop / new criticals fire.

### 4.3 What “score” means

- Starts from a base (default **100**).  
- Deducts for **critical / warning / info** with weights.  
- On larger crawls, page-level issues use **prevalence** (share of pages affected), with a cap so huge crawls cannot zero the score by volume alone.  
- Reports label **provisional / not-run signals** honestly via `signal_trust` — blank or “Not run” beats fake metrics.

---

## 5. Analyzers (SEO checks)

Registered in `app/analyzers/registry.py` → `build_default_registry()`.

| Analyzer | What it checks |
|----------|----------------|
| **title** | Missing / short / long titles |
| **meta_description** | Missing / length issues |
| **headings** | Missing H1, multiple H1, structure |
| **image_alt** | Content images missing `alt` (decorative `alt=""` and `<source>` excluded) |
| **canonical** | Missing / inconsistent canonicals |
| **links** | Internal graph: orphans, hubs, dead-ends (crawl-scoped) |
| **page_size** | Oversized HTML |
| **robots** | robots.txt fetch + directives |
| **sitemap** | sitemap.xml presence / basic validation |
| **schema** | JSON-LD parse; missing types; **schema advisor** suggests Organization/WebSite/Article/Product/FAQ/WebPage by page kind |

Supporting modules:

- `recommendations.py` — prescriptive actions (not just “fix title”)  
- `rendering_guardrails.py` — SPA false-positive protection  
- `scorer.py` / `metrics.py` — score + structured metrics for dashboard

Each analyzer returns `AnalyzerResult` with `issues[]` (`code`, `severity`, `message`, `url`, …). Dashboard **Analyzers** panel drills into those issues.

---

## 6. Recommendations accuracy rules

Plan Perfect accuracy rules (enforced in code + tests under `tests/fixtures/rec_accuracy/`):

1. **Never invent metrics** — empty/error with reason beats fake numbers.  
2. **Every action cites evidence** — page URL, field, current and/or suggested value (or GSC query row).  
3. **Do not contradict the page** — e.g. never emit `missing_title` when a title exists.  
4. **Page kind aware** — `/privacy` / legal pages do **not** get homepage marketing meta copy.  
5. **Unrendered JS shell** — only recommend enabling JS rendering; skip on-page rewrites.  
6. **Paid APIs stay opt-in** — SERP/backlinks never auto-run; **402** means fund DataForSEO, not “feature broken.”  
7. **Mobile PageSpeed preferred** when PSI runs (`PAGESPEED_STRATEGY=mobile`).

Optimize / keyword-placement LLM calls must stay grounded in extracted page facts.

---

## 7. External integrations

### 7.1 Google OAuth (“Connect Google”)

- One OAuth Web client for the product (`secrets/google-oauth-client.json` or `GSC_CLIENT_ID` / `GSC_CLIENT_SECRET`).  
- Customers only click Connect; they never open Google Cloud Console.  
- Tokens stored per **`account_id`** (nickname, e.g. `demo`) in `GSC_TOKEN_DB_PATH` (default `data/gsc_tokens.db`).  
- Flow:  
  1. `GET /auth/google/start?account_id=…`  
  2. Google consent → `GET /auth/callback`  
  3. `GET /gsc/sites`, `GET /gsc/performance`  
  4. Pass `gsc_account_id` into audits / dashboard  

Same OAuth unlocks **GA4** when Analytics Admin + Data APIs are enabled and the user re-consents for `analytics.readonly` if needed.

Production checklist: `GET /auth/google/production`. Privacy stub: `GET /legal/privacy`.  
Hosted redirect must be HTTPS: `GSC_REDIRECT_URI=https://YOUR_DOMAIN/auth/callback`.

### 7.2 Google Analytics 4

| Endpoint | Role |
|----------|------|
| `GET /ga4/properties` | List properties for `account_id` |
| `PUT /ga4/preference` | Save default property |
| `GET /ga4/report` | Sessions / users / top pages snapshot |

Dashboard shows a short **“So what”** narrative from real totals — **no invented revenue** unless conversion fields exist in the snapshot.

### 7.3 PageSpeed Insights

- Free Google API key: `GOOGLE_PAGESPEED_API_KEY`  
- `GET /pagespeed?url=…` and audit seed enrichment  
- Strategy: `PAGESPEED_STRATEGY=mobile` (default preference)

### 7.4 DataForSEO

Shared login/password:

- **Keywords Data + Labs** — volume, CPC, competition, difficulty, related  
- **Competitive** — SERP, rank check, backlinks (paid; opt-in)

If the account lacks funds, APIs may return **402 Payment Required**. UI should say “fund DataForSEO,” not pretend the panel is empty by bug.

### 7.5 LLM (OpenAI-compatible)

- `OPENAI_API_KEY`, optional `LLM_BASE_URL` / `LLM_MODEL`  
- Used for **optimize advice** and **keyword placement** — never for silently inventing crawl metrics.

---

## 8. How to run (local)

### 8.1 Python

Requires **Python 3.11+** (3.12 recommended).

```bash
cd SEO-Agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional extras
pip install -e ".[playwright,pdf,postgres]"
playwright install chromium   # if using Playwright
```

Copy env:

```bash
cp .env.example .env
# Edit .env — never commit it
```

### 8.2 Start API + Dashboard

```bash
seo-api
# or: uvicorn app.api.app:app --reload --port 8000
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/health | Health |
| http://localhost:8000/docs | OpenAPI |
| http://localhost:8000/dashboard/ui?url=https://example.com/ | Dashboard |
| http://localhost:8000/ | Redirects to dashboard |

If `SEO_API_KEY` and/or `SEO_API_CLIENTS` is set, protected routes need:

```http
Authorization: Bearer <key>
# or
X-API-Key: <key>
```

- **`SEO_API_KEY`** — admin / wildcard (any `account_id`).
- **`SEO_API_CLIENTS`** — FP-6 lite map of `account_id` → client key (JSON or `id=key,id2=key2`). Client keys cannot read another customer's GSC/GA4/`gsc_account_id`.
- **`GET /auth/me`** — returns `{role, account_id}` for the caller.
- **`/dashboard/ui`** stays public; **`GET /dashboard`** JSON requires a key when auth is on.

The dashboard has an **API key** field that stores the key in the browser for subsequent calls (including Load dashboard).

### 8.3 Docker

```bash
docker compose up --build
curl -sS http://127.0.0.1:8000/health
```

Mount/persist `/data` (or host `data/`) so audits and GSC tokens survive restarts. See `docs/HOSTING.md`.

---

## 9. Dashboard — how to use it

Open:

```text
http://localhost:8000/dashboard/ui?url=https://YOUR_SITE/&gsc_account_id=demo
```

Every panel has an **i** help popover. Full beginner labels: `docs/understand.md`.

### 9.1 Top controls

| Control | What it does |
|---------|----------------|
| **Site URL** | Seed URL to audit / load |
| **Google account_id** | Connect Google nickname for GSC/GA4 |
| **API key** | Matches server `SEO_API_KEY` (admin) or a `SEO_API_CLIENTS` key |
| **GA4 property** | Pick + save preferred property |
| **Load dashboard** | Assemble last saved signals for URL |
| **Run audit** | Crawl + analyze + enrich (per options) |
| **Get optimize advice** | LLM title/meta/H1 suggestions (does not change live site) |
| **Keyword position tracker** | Paid rank/SERP for keywords → Rank / SERP / history panels |
| **Get keyword placement** | On-page slots for a keyword (different from rank!) |
| **Schedules** | Create / pause / delete / run-due recurring audits |
| **Crawl presets** | Quick (3) / Standard (15, default) / Deep (50) |

### 9.2 Typical operator workflow

1. Set URL + API key (+ `account_id` if Google connected).  
2. Choose Standard crawl (or Deep for larger sites).  
3. **Run audit** → read **Site audit** score + **Top issues** + **Recommendations**.  
4. Open **Search Console** / **GA4** for real demand & traffic.  
5. Use **Keyword research** for volume/CPC; **placement** for on-page; **position tracker** only when DataForSEO is funded.  
6. Create a **schedule** for retainer monitoring; optionally set alert webhook.  
7. **Share** / PDF for client handoff.

### 9.3 Two keyword features (do not confuse)

| Feature | Question |
|---------|----------|
| **Position tracker** | Where do I rank on **Google**? |
| **Keyword placement** | Where should this word appear on **my page**? |

---

## 10. HTTP API catalog (contributor cheat sheet)

Interactive docs: `/docs`. Summary:

### Core

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Public |
| POST | `/audit` | Sync audit; `background=true` for job |
| GET | `/jobs/{job_id}` | Poll durable job |
| POST | `/optimize` | AI page optimization advice |
| POST | `/keyword-plan` | Keyword placement plan |
| POST | `/report` | Build report from URL or audit_id |
| GET | `/report/{audit_id}` | Saved report (`?format=pdf` optional) |
| GET | `/history?url=` | Past audits |
| POST | `/compare` | Diff vs previous |

### Google

| Method | Path |
|--------|------|
| GET | `/auth/google/start` |
| GET | `/auth/callback` |
| GET | `/auth/google/status` |
| GET | `/auth/google/production` |
| POST | `/auth/google/disconnect` |
| GET | `/legal/privacy` |
| GET | `/gsc/sites` |
| GET | `/gsc/performance` |
| GET | `/ga4/status` |
| GET | `/ga4/properties` |
| GET/PUT | `/ga4/preference` |
| GET | `/ga4/report` |

### Insights & competitive

| Method | Path |
|--------|------|
| GET | `/pagespeed` / `/pagespeed/status` |
| GET | `/keywords/status` `/research` `/difficulty` `/related` |
| GET | `/competitive/status` |
| GET | `/serp` `/rank` `/rank/history` `/backlinks` |

### Retainer / product surface

| Method | Path |
|--------|------|
| GET | `/dashboard` (JSON) · `/dashboard/ui` (HTML) |
| GET | `/trends` |
| GET/POST/DELETE | `/schedules` (+ enabled, run-due) |
| POST | `/report/{audit_id}/share` | Create public **client scorecard** link |
| GET | `/share/{token}` | Scorecard HTML (default); `?format=pdf` / `markdown` |
| GET | `/alerts/status` · POST `/alerts/test` |
| GET | `/crawl/login-wall` |

**API key middleware:** when `SEO_API_KEY` is set, most routes require Bearer / X-API-Key. Exceptions include health, docs, share links, dashboard UI shell, and Google OAuth start/callback (see `app/api/auth.py`).

---

## 11. CLI usage

Installed via `pip install -e .` entry points in `pyproject.toml`:

```bash
# Audit
seo-audit https://example.com -o out.json --max-pages 15
seo-audit https://example.com --save --max-pages 15
seo-audit https://example.com --compare --max-pages 15

# Optimize (needs OPENAI_API_KEY)
seo-optimize https://example.com -o optimize.json --keywords "brand,product"

# Reports
seo-report --url https://example.com -o report.md --max-pages 5
seo-report --audit-id <id> -f pdf -o report.pdf

# History / compare
seo-history https://example.com
seo-compare https://example.com -o changes.md
```

Local dump files like `out.json` / `optimize.json` are **gitignored** — keep them off commits.

---

## 12. Configuration

### Precedence

1. `config/default.yaml` defaults  
2. Environment variables / `.env` (see `.env.example`)  
3. Per-request **AuditOptions** from API / dashboard / CLI flags  

### Critical env vars

| Variable | Role |
|----------|------|
| `SEO_API_KEY` | Lock API in any non-local exposure |
| `SEO_STORAGE_PATH` / `SEO_DATABASE_URL` | SQLite path or Postgres |
| `SEO_PLAYWRIGHT_ENABLED` | Prefer JS rendering |
| `GSC_*` | OAuth client, redirect URI, token DB, publishing status |
| `GOOGLE_PAGESPEED_API_KEY` | CWV |
| `KEYWORD_API_LOGIN` / `PASSWORD` | DataForSEO |
| `OPENAI_API_KEY` | Optimize / placement |
| `SEO_ALERT_WEBHOOK_URL` | Schedule/compare alerts |
| `PORT` / `SEO_BIND_HOST` | Hosted bind |

Secrets directories (`secrets/`, `.env`, `*.db`) must stay local or in the host’s secret store — never GitHub.

---

## 13. Storage, jobs, schedules, alerts

| Concern | Behavior |
|---------|----------|
| **Audits** | SQLite default (`data/audits.db`) or Postgres via `SEO_DATABASE_URL` |
| **Jobs** | Durable queue for `background=true` audits and due schedules |
| **Schedules** | Interval audits; dashboard can create / pause / delete / run-due |
| **Share links** | Tokenized public report URLs |
| **Rank history** | `rank_snapshots` over time for position tracker |
| **GSC tokens** | Separate SQLite (`gsc_tokens.db`) keyed by `account_id` |
| **Alerts** | Webhook when score drops or new criticals appear vs previous |

Workers start with the API lifespan (`JobRunner.start`, `start_scheduler`).

---

## 14. Authenticated crawl (limits)

- Opt-in only: `use_authenticated_crawl` + cookie and/or headers.  
- Credentials stay **in-memory for that request** — not written to disk by design.  
- Applied on GET/HEAD crawl fetches.  
- `GET /crawl/login-wall` dry-runs detection **without** credentials.  
- Analytics cookies are **not** session cookies — they will not unlock a login wall.  
- Full form-login / Playwright login automation is **out of scope** for current v1.

---

## 15. Rendering / Playwright

- Many modern sites (React/Vue/Next) ship a thin shell; without JS, titles/H1 look “missing.”  
- Install Playwright extra + Chromium; set `SEO_PLAYWRIGHT_ENABLED=true` (or rely on SPA auto-trigger when installed).  
- Guardrails prevent false criticals on unrendered shells and tell operators to enable rendering.

Docker image used for hosting should include Playwright Chromium for SPA customers.

---

## 16. Reports & trust

- **Markdown / JSON / PDF** from the same audit object.  
- `app/reports/signal_trust.py` ensures skipped integrations show as **Not run / Unavailable / Error**, not silent omission.  
- PDF needs `pip install 'seo-agent[pdf]'` (or Docker image with pdf extra).  
- Public handoff: create share token → `GET /share/{token}` (optional `?format=pdf`).

---

## 17. Internal tools registry

`app/tools/registry.py` registers named Python functions (`audit_site`, `crawl_site`, `optimize_page`, `check_pagespeed`, GSC/GA4 helpers, SERP/rank/backlinks, trends, …).

- CLI and services call these tools.  
- HTTP routes wrap the same services.  
- When embedding in another product, prefer the **HTTP API** as the stable boundary; treat `app/tools` as an in-process convenience layer.

---

## 18. Testing

```bash
pytest -q
```

Notable accuracy coverage:

- `tests/unit/analyzers/test_recommendation_accuracy.py`  
- Fixtures: `tests/fixtures/rec_accuracy/` (Actoro-like home, privacy, complete page)

Guidelines for contributors:

- New recommendation codes must go through `_action(...)` so **evidence** is always present.  
- Do not invent metrics in dashboard renderers — show trust/empty states.  
- Prefer unit tests for analyzers; keep secrets out of fixtures.

---

## 19. Embedding in a larger product

This engine is intentionally API-first:

1. Run `seo-api` as an internal service (Docker).  
2. Parent product owns users, billing, and primary UI.  
3. Parent calls `/audit`, `/dashboard` JSON, GSC/GA4, etc. with a service API key.  
4. Either:  
   - Users Connect Google via this service’s OAuth redirect on **your** HTTPS domain, or  
   - Parent brokers OAuth and stores/`account_id` mapping consistently.  

The bundled `dashboard.html` is a full operator console; production UX can be thinner and call the same endpoints.

---

## 20. What is intentionally out of scope (today)

| Deferred | Notes |
|----------|--------|
| Stripe / self-serve SaaS billing | Parent product or later Fast path |
| Playwright form login | Auth crawl is cookie/header only |
| Auto “apply fixes to CMS” | Advice only |
| GEO / AI-citation product | Future |
| Invented revenue / fake ranks | Never |

---

## 21. Contributor checklist (before PR)

- [ ] No `.env`, `secrets/`, `*.db`, or real API keys in the commit  
- [ ] New behavior reflected in `/docs` OpenAPI and, if UI-facing, `docs/understand.md`  
- [ ] Recommendations include evidence; add/adjust golden fixtures if logic changes  
- [ ] Paid paths remain opt-in; 402 messaging stays honest  
- [ ] `pytest -q` passes locally  
- [ ] Dashboard still works against `seo-api` with and without optional keys unset (empty states)

---

## 22. Quick mental model

```text
Crawl truth → Analyzer issues → Honest score
     ↓
Recommendations with evidence
     ↓
Optional real-world signals (GSC / GA4 / PSI / DataForSEO)
     ↓
Dashboard + PDF/share for humans; HTTP API for products
```

If a panel is empty, ask: **Was the integration configured? Was it opted in? Did the provider return an error?**  
The agent prefers an explained empty state over a confident lie.

---

*File: `allinfo.md` — contributor deep dive for SEO Agent (Dashboard + API). Keep secrets out of git.*
