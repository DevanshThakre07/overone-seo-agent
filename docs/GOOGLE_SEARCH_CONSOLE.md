# SEO Agent — APIs & Google Search Console reference

Credentials and external APIs needed to make this agent production-grade, plus how Connect Google / Search Console works.

---

## All APIs we need (master checklist)

### Already in use (no extra SEO API)

| Piece | Purpose | Env / notes | Status |
|-------|---------|-------------|--------|
| **OpenAI-compatible LLM** | AI optimize / rewrites | `OPENAI_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Wired |
| **Playwright / Chromium** | JS-rendered pages | `SEO_PLAYWRIGHT_ENABLED=true` + `playwright install chromium` | Wired |
| **Our FastAPI / Hermes tools** | Crawl → analyze → report | Local / deploy | Wired |

### Tier 1 — Free Google APIs (highest priority)

| API | What it unlocks | Auth type | Env vars | Status |
|-----|-----------------|-----------|----------|--------|
| **Google Search Console API** | Real queries, clicks, CTR, position, index/property list, page-2 opportunities | OAuth 2.0 (per customer) | `GSC_CLIENT_SECRETS_FILE`, `GSC_REDIRECT_URI`, `GSC_TOKEN_DB_PATH`, optional `GSC_CLIENT_ID` / `GSC_CLIENT_SECRET` | **Wired** (Connect Google) |
| **PageSpeed Insights API** | Lighthouse + lab Core Web Vitals (LCP, CLS, INP) | API key | `GOOGLE_PAGESPEED_API_KEY`, optional `PAGESPEED_STRATEGY` | **Wired** |
| **Chrome UX Report (CrUX)** | Real-user field vitals | API key | `GOOGLE_CRUX_API_KEY` | Not built yet |
| **Google Analytics Data API (GA4)** | Traffic snapshot (sessions / users / top pages) | OAuth 2.0 (`analytics.readonly`) | Reuse Connect Google `account_id`; enable Admin + Data APIs | ✅ `/ga4/*` + preferred property picker |
| **Bing Webmaster Tools** (optional) | Bing queries / index | API key | `BING_WEBMASTER_API_KEY` | Not built yet |

**Enable in Google Cloud → APIs & Services → Library:**

- Google Search Console API ✅ (you enabled this)
- PageSpeed Insights API
- Chrome UX Report API
- Google Analytics Data API (if using GA4)

Same OAuth **Web application** client can later request extra scopes (GSC + GA4) if you want one “Connect Google” for customers.

### Tier 2 — One paid keyword / competitive API

Pick **one** primary provider (recommended: **DataForSEO**).

| Provider | Unlocks | Env vars | Status |
|----------|---------|----------|--------|
| **DataForSEO** (recommended) | Keyword volume, CPC, competition + Labs difficulty/related | `KEYWORD_API_PROVIDER=dataforseo`, `KEYWORD_API_LOGIN`, `KEYWORD_API_PASSWORD` | **Wired** (Keywords Data + Labs) |
| **Google Ads Keyword Planner** | Official volume ranges | `KEYWORD_API_PROVIDER=google_ads`, `GOOGLE_ADS_DEVELOPER_TOKEN`, OAuth client/refresh, `GOOGLE_ADS_CUSTOMER_ID` | Not built |
| **Semrush** | Volume, difficulty, related | `KEYWORD_API_PROVIDER=semrush`, `KEYWORD_API_KEY` | Not built |
| **Ahrefs** | Volume, difficulty, backlinks | `KEYWORD_API_PROVIDER=ahrefs`, `KEYWORD_API_KEY` | Not built |

Without this tier, optimize/audit must **not** invent search volume — only keyword *placement* on the live page.

### Tier 3 — Infrastructure / reliability

| Service | Why | Env vars | Status |
|---------|-----|----------|--------|
| **Scraper proxy** (ScraperAPI / Zyte / Bright Data) | Avoid 403 / bot blocks on big sites | `SCRAPER_API_KEY` or `SCRAPER_PROXY_URL` | Not built |
| **API auth for our FastAPI** | Stop open crawl endpoints | `SEO_API_KEY` (Bearer / `X-API-Key`) | **Wired** (off when unset) |
| **Postgres** (4A) | Optional production storage for audits + jobs | `SEO_DATABASE_URL` / `DATABASE_URL` | SQLite default local/dev |
| **Worker queue** (4A) | Durable DB-backed jobs (`pending|running|completed|failed`) | same DB as storage | Thread workers in `seo-api`; Celery/Redis still optional later |

### Suggested build order

1. Search Console Connect ✅ → **verify a real property** *(your step)*  
2. PageSpeed Insights ✅  
3. Hermes tools for PageSpeed ✅ (`check_pagespeed`)  
4. Feed GSC opportunities into recommendations ✅ (code; needs verified property for live data)  
5. DataForSEO Keyword Data ✅ (`research_keywords`, `/keywords/research`)  
6. DataForSEO Labs ✅ (difficulty + related)  
7. CrUX / GA4  
8. API auth ✅ (`SEO_API_KEY`)  
9. Proxy + Production OAuth publish (checklist + `/auth/google/production` ✅; Cloud Publish = owner)  

---

## PageSpeed Insights (wired)

### What it does

Calls Google's PageSpeed Insights API for the **audit seed URL** (mobile by default) and adds:

- Lighthouse **performance score**
- Lab **LCP / CLS / INP** (and TBT/FCP helpers)
- Field data when Google returns it (`loadingExperience`)
- Warning issues that feed the audit score: `pagespeed_low_performance`, `pagespeed_poor_lcp`, `pagespeed_poor_cls`, `pagespeed_poor_inp`

No OAuth — only an API key. If the key is missing, audits skip PSI cleanly.

### Setup

1. Google Cloud → **APIs & Services → Library** → enable **PageSpeed Insights API**
2. **Credentials → Create credentials → API key** (optionally restrict to PageSpeed API)
3. `.env`:
   ```bash
   GOOGLE_PAGESPEED_API_KEY=your_key_here
   PAGESPEED_STRATEGY=mobile
   ```
4. Restart `seo-api`

### Endpoints

- `GET /pagespeed/status`
- `GET /pagespeed?url=https://example.com`
- `GET /pagespeed?url=https://example.com&strategy=both`
- Audits: auto-runs when key is set; disable per request with `"pagespeed": false`

### Notes

- PSI is **slow** (often 15–60s) and rate-limited — we only hit the seed URL, not every crawled page.
- `PAGESPEED_STRATEGY`: `mobile` | `desktop` | `both`
- **Config decision — default `mobile`:** Google’s ranking / Core Web Vitals signals are **mobile-first**, so audits and `check_pagespeed` default to mobile. `both` roughly **doubles** PSI API time and quota. Desktop is available via `strategy=desktop` or `strategy=both` (API query, Hermes arg, or `.env`) for deep checks, but is **intentionally not** run by default on every audit.

---

## Google Search Console & OAuth — how it works

### Mental model

| Who | What they do |
|-----|----------------|
| **You (product owner)** | Create **one** OAuth client in Google Cloud. Enable APIs. Later publish the app to Production. |
| **Customers** | Already have their site in **their** Search Console. Click **Connect Google** in your product and approve. They never open Google Cloud Console or create client IDs. |

You do **not** need to add your own website to Search Console just to build the product. GSC data always comes from the **customer’s** verified property after they connect.

### What we already built (GSC)

- OAuth client secrets: `secrets/google-oauth-client.json` (gitignored)
- Env vars (see `.env.example`): `GSC_CLIENT_SECRETS_FILE`, `GSC_REDIRECT_URI`, `GSC_TOKEN_DB_PATH`, optional `GSC_CLIENT_ID` / `GSC_CLIENT_SECRET`
- Tokens per customer: `data/gsc_tokens.db`
- API routes:
  - `GET /auth/google/start?account_id=...` — start Connect Google
  - `GET /auth/callback` — OAuth callback
  - `GET /auth/google/status?account_id=...`
  - `POST /auth/google/disconnect?account_id=...`
  - `GET /gsc/sites?account_id=...`
  - `GET /gsc/performance?account_id=...&site_url=...`
  - `POST /audit` with `gsc_account_id` — crawl audit + GSC enrichment

Without Connect Google, **technical crawl audits still work**. GSC-only features (real queries, clicks, CTR, position, page-2 opportunities) need a connected account + verified property.

### Local GSC setup checklist

1. Google Cloud project with **Search Console API** enabled.
2. OAuth client type: **Web application**.
3. **Authorised redirect URIs** (must match exactly):
   - Local: `http://localhost:8000/auth/callback`
   - Optional: `http://127.0.0.1:8000/auth/callback`
4. **Authorised JavaScript origins** (optional for local):
   - `http://localhost:8000`
5. `.env`:
   ```bash
   GSC_CLIENT_SECRETS_FILE=secrets/google-oauth-client.json
   GSC_REDIRECT_URI=http://localhost:8000/auth/callback
   GSC_TOKEN_DB_PATH=data/gsc_tokens.db
   ```
6. Start API: `seo-api` or `uvicorn app.api.app:app --reload --port 8000`
7. Open: `http://localhost:8000/auth/google/start?account_id=demo`
8. List sites: `http://localhost:8000/gsc/sites?account_id=demo`  
   (empty `sites: []` = Google connected, but no verified Search Console property yet)

### Common GSC / OAuth errors

| Error | Meaning | Fix |
|-------|---------|-----|
| `redirect_uri_mismatch` | Callback URL not registered (or not identical) | Add exact `GSC_REDIRECT_URI` under OAuth client redirect URIs |
| `access_denied` / “has not completed the Google verification process” | App is in **Testing**; user is not a test user | OAuth consent screen → **Test users** → add that Google email |
| Passkey / iCloud prompt | Normal Google sign-in | Complete passkey, or Cancel → More ways to verify → password |
| Connected but `"sites":[]` | Account has no verified Search Console property | Customer verifies their site in Search Console, then call `/gsc/sites` again |

### Testing vs Production (important for customers)

#### While status = Testing

- Only emails listed under **Test users** can Connect Google.
- Fine for you + a few beta testers.
- **Real customers should not be expected to be added as test users.**
- SEO-Agent defaults `GSC_OAUTH_PUBLISHING_STATUS=testing` so Connect Google / status APIs warn honestly.

#### When you go live

1. Publish OAuth consent screen to **Production** (checklist below).
2. Complete **Google verification** if required for your scopes (Search Console + Analytics readonly usually need it for broad public use).
3. Set env to match Cloud Console, restart `seo-api`.
4. After that, customers only: Connect Google → Allow. No Cloud Console, no test-user list.

#### After you deploy the app somewhere

1. Add production callback in Google Cloud, e.g. `https://yourdomain.com/auth/callback`.
2. Set `GSC_REDIRECT_URI` to that **same** URL.
3. Keep local `http://localhost:8000/auth/callback` if you still develop locally (both can be listed).

### OAuth Production publish checklist

> **Owner-owned in Google Cloud.** Code cannot flip Publishing status for you.  
> Track progress: `GET /auth/google/production` · privacy stub: `GET /legal/privacy`

| # | You do (Google Cloud / hosting) | SEO-Agent env / endpoint |
|---|----------------------------------|---------------------------|
| 1 | OAuth consent screen: app name, support email, logo, developer contact | — |
| 2 | Application home page URL (HTTPS) | `GSC_HOMEPAGE_URL=https://YOUR_DOMAIN/` |
| 3 | Privacy policy URL (HTTPS, public) | Deploy seo-api → use `https://YOUR_DOMAIN/legal/privacy` **or** your own page; set `GSC_PRIVACY_POLICY_URL` to the same URL you paste in Cloud |
| 4 | Authorized domains = your product domain | — |
| 5 | OAuth client redirect URI = `https://YOUR_DOMAIN/auth/callback` (+ keep localhost for dev) | `GSC_REDIRECT_URI=https://YOUR_DOMAIN/auth/callback` |
| 6 | Enable APIs: Search Console, Analytics Admin, Analytics Data (+ PageSpeed if used) | — |
| 7 | Consent screen → **Publish app** → Production | `GSC_OAUTH_PUBLISHING_STATUS=production` then restart `seo-api` |
| 8 | Submit **verification** if Google asks (sensitive scopes) | Justify `webmasters.readonly` + `analytics.readonly`; demo video of Connect Google → Allow → `/gsc/sites` |
| 9 | Protect the API on the public host | `SEO_API_KEY=...` (OAuth start/callback + `/legal/*` stay public) |

**Scopes we request (sensitive):**

- `https://www.googleapis.com/auth/webmasters.readonly`
- `https://www.googleapis.com/auth/analytics.readonly`
- `openid` / `email` (account label)

**What “done” looks like**

```bash
curl -s http://localhost:8000/auth/google/production | python -m json.tool
# publishing_status: production
# production_ready: true
# customer_access: any_google_account
# blocking: []
```

Connect Google HTML stops warning about Test users once `GSC_OAUTH_PUBLISHING_STATUS=production`.  
`access_denied` while still Testing returns a clear HTML hint to add Test users.

### Customer journey (GSC)

1. Customer already verified their site in [Google Search Console](https://search.google.com/search-console).
2. In your product they click **Connect Google**.
3. They approve SEO-Agent to read Search Console (readonly).
4. Your backend stores their refresh token under their `account_id`.
5. Audits / reports use `gsc_account_id` to pull queries, clicks, CTR, position, opportunities.

### What still works without GSC / paid APIs

- Crawl, extract, analyzers, score, Markdown report
- `optimize_page` / keyword *placement* (not paid keyword research volume)
- Hermes tools that do not need Search Console

---

## Env template (all planned keys)

Copy into `.env` as you enable each integration (never commit secrets):

```bash
# --- Already used ---
OPENAI_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
SEO_PLAYWRIGHT_ENABLED=true

# --- Google Search Console (wired) ---
GSC_CLIENT_SECRETS_FILE=secrets/google-oauth-client.json
GSC_REDIRECT_URI=http://localhost:8000/auth/callback
GSC_TOKEN_DB_PATH=data/gsc_tokens.db
# GSC_CLIENT_ID=
# GSC_CLIENT_SECRET=

# --- PageSpeed / CrUX ---
GOOGLE_PAGESPEED_API_KEY=
PAGESPEED_STRATEGY=mobile
# GOOGLE_CRUX_API_KEY=

# --- Keyword research (DataForSEO) ---
KEYWORD_API_PROVIDER=dataforseo
KEYWORD_API_LOGIN=
KEYWORD_API_PASSWORD=
# KEYWORD_LOCATION_CODE=2840
# KEYWORD_LANGUAGE_CODE=en

# --- GA4 (planned) ---
# GA4_PROPERTY_ID=
# GA4_CLIENT_ID=
# GA4_CLIENT_SECRET=
# GA4_REFRESH_TOKEN=

# --- API auth (protect seo-api when exposed) ---
# SEO_API_KEY=

# --- Crawl hardening (planned) ---
# SCRAPER_API_KEY=
# SCRAPER_PROXY_URL=
```

### Reminder — `SEO_API_KEY`

This is **our** password for the FastAPI (`seo-api`), not a Google / DataForSEO / Hermes key.

| Situation | What to do |
|-----------|------------|
| **Local / Hermes only** | Leave `SEO_API_KEY` empty or commented out. Auth is off. |
| **API exposed** (deploy, public URL, shared network) | Set a long random secret in `SEO-Agent/.env`, restart `seo-api`, and send `Authorization: Bearer <key>` or `X-API-Key: <key>` on protected routes. |

Public without the key: `/health`, `/docs`, `/auth/google/start`, `/auth/callback`. Generate one with e.g. `openssl rand -hex 32`.

---

## Do not commit

- `secrets/`
- `.env`
- `data/gsc_tokens.db` (customer tokens)
- Any downloaded `client_secret_*.json`

---

## Project status board (living)

> **Maintain this section** after every completed task: move items Done ↔ Todo, update “How it works”, and note new env vars / endpoints. Last updated: **2026-08-08** (Hermes GSC tools).

### Snapshot

| Area | Status | Notes |
|------|--------|--------|
| Core crawl → analyze → score → report | ✅ Done | FastAPI + Hermes plugin |
| LLM optimize / keyword *placement* | ✅ Done | Needs `OPENAI_API_KEY` for optimize |
| Google Search Console Connect + client | ✅ Done | OAuth wired; live data needs property verify |
| GSC → recommendations loop | ✅ Done | Needs verified property + `gsc_account_id` |
| PageSpeed Insights / Core Web Vitals | ✅ Done | API key; seed URL only |
| Hermes `check_pagespeed` | ✅ Done | Restart Hermes session to load |
| DataForSEO Keywords Data (volume/CPC) | ✅ Done | Login + password; pay-as-you-go |
| DataForSEO Labs (difficulty / related) | ✅ Done | Same credentials; enriches `/keywords/research` |
| Hermes `research_keywords` | ✅ Done | Volume + difficulty + related |
| Hermes smoke (keywords + PageSpeed + audit_site + keyword_plan) | ✅ Done | Confirmed 2026-08-07 |
| Hermes GSC tools (`gsc_status` / `gsc_sites` / `gsc_performance`) | ✅ Done | OAuth still via browser/`seo-api` |
| API auth (`SEO_API_KEY`) | ✅ Done | Bearer / `X-API-Key`; off when unset |
| CrUX (standalone field vitals) | ❌ Todo | Overlaps PSI field data |
| GA4 traffic (properties + report + preferred picker) | ✅ | `PUT /ga4/preference`; audits can omit property_id |
| Scraper proxy | ❌ Todo | Big-site 403s |
| Production OAuth publish | 🔶 Code/docs ✅ | Owner still Publishes in Google Cloud + sets `GSC_OAUTH_PUBLISHING_STATUS` |
| Postgres + worker queue | ✅ 4A + F | Audits/jobs/schedules/shares; due schedules → `/jobs` |

---

### Done — what we shipped

1. **SEO engine core** — crawl, extract, analyzers, scoring, Markdown/JSON reports, SQLite history.
2. **Hermes plugin** (`integrations/hermes/seo_agent_plugin`) — tools without editing `hermes-agent` source.
3. **Connect Google / GSC** — OAuth Web client, token store per `account_id`, `/gsc/sites`, `/gsc/performance`, audit enrichment via `gsc_account_id`. Demo account connects; `sites: []` until a property is verified.
4. **GSC → recommendations** — page-2 + low-CTR opportunities merge into `recommendations[].actions` (`gsc_page2_opportunity`, `gsc_low_ctr`). Hermes `audit_site` accepts `gsc_account_id`. Still needs a **verified** Search Console property matching the seed URL.
4b. **Hermes GSC tools** — `gsc_status`, `gsc_sites`, `gsc_performance` (thin wrappers over `GoogleSearchConsoleService`). Connect Google still uses `/auth/google/start` in the browser.
5. **PageSpeed Insights** — `GOOGLE_PAGESPEED_API_KEY`; `/pagespeed`, `/pagespeed/status`; auto on audit seed URL; Hermes `check_pagespeed`.
6. **DataForSEO Keywords Data** — volume, CPC, competition via `/keywords/research`.
7. **DataForSEO Labs** — `keyword_difficulty` (0–100) + related/long-tail ideas; `/keywords/difficulty`, `/keywords/related`; auto-merged into `/keywords/research` and Hermes `research_keywords` (same login/password).
8. **API auth** — set `SEO_API_KEY` to require `Authorization: Bearer …` or `X-API-Key` on protected routes; `/health`, `/docs`, `/auth/google/start`, `/auth/callback` stay public. Unset = open (local/dev). `/health` reports `api_auth_required`.

---

### Todo — what still needs doing

| Priority | Task | Blocked by |
|----------|------|------------|
| **Next** | **Verify a GSC property** for a real site (Search Console) so enrichment returns data | You own a verified property matching the audit URL |
| Done (A) | GA4 properties + report | Reuse Connect Google; CrUX still later |
| Later | Scraper proxy | Vendor account |
| Later | Production OAuth + deploy redirect URI | Hosting domain — checklist `#oauth-production-publish-checklist` |
| Done (4A) | Postgres + durable job queue | SQLite still default local/dev |

---

### What we use (stack & vendors)

| Layer | What | Role |
|-------|------|------|
| **Runtime** | Python, FastAPI (`seo-api`), SQLite | Local API + storage |
| **Host agent** | Hermes plugin → SEO-Agent tools | Chat: audit, pagespeed, keywords, optimize… |
| **LLM** | OpenAI-compatible (`OPENAI_API_KEY`) | Page rewrite suggestions |
| **Render** | Playwright (optional) | JS-heavy sites |
| **Google — GSC** | Search Console API + OAuth | Customer queries / CTR / position |
| **Google — PSI** | PageSpeed Insights API key | Lab + field Core Web Vitals |
| **DataForSEO — Keywords Data** ✅ | `google_ads/search_volume/live` | Volume, CPC, competition |
| **DataForSEO — Labs** ✅ | `bulk_keyword_difficulty` + `related_keywords` | Difficulty 0–100, related ideas |
| **DataForSEO — SERP / Backlinks** ✅ | `serp/google/organic/live/regular` + `backlinks/summary` + `referring_domains` | Opt-in only (`/serp`, `/rank`, `/backlinks`, Hermes tools, audit flags) |
| **CrUX / GA4 / Bing / proxy** | Planned | See checklist above |

**Why Labs (in addition to Keywords Data):**

| API | Answers |
|-----|---------|
| Keywords Data | How many people search this term? What’s CPC/ads competition? |
| Labs difficulty | How hard is it to rank in Google’s organic top 10? (0–100) |
| Labs related | What other queries should we consider (Google “related searches”)? |

**Independent tools (no required order):**

- URL → `/pagespeed` (speed)
- Keywords → `/keywords/research` (volume + difficulty + related)
- Difficulty only → `/keywords/difficulty`
- Related only → `/keywords/related?keyword=…`
- Full site → `POST /audit` (crawl; PSI auto if key set; keyword research if `target_keywords` passed)

---

### How everything works (end-to-end)

```text
Customer / you
    │
    ├─ FastAPI docs (localhost:8000/docs)
    │     /pagespeed?url=…             → Google PSI
    │     /keywords/research?…         → Keywords Data + Labs
    │     /keywords/difficulty?…       → Labs difficulty only
    │     /keywords/related?keyword=…  → Labs related only
    │     /auth/google/start           → GSC OAuth (per account_id)
    │     POST /audit                  → crawl + analyzers + optional PSI + optional GSC
    │
    └─ Hermes chat
          check_pagespeed / research_keywords / audit_site / …
                → same SEO-Agent services (in-process plugin)
```

| Feature | Input | External call | Output |
|---------|-------|---------------|--------|
| PageSpeed | Page URL | Google PSI | Score, LCP/CLS/INP, issues |
| Keyword research | Comma-separated terms | Keywords Data + Labs | Volume, CPC, difficulty, related |
| Keyword difficulty | Terms | Labs bulk difficulty | 0–100 scores |
| Related keywords | One seed | Labs related | Related/long-tail ideas |
| Keyword *placement* | URL + terms | Our crawl only | Where terms appear on the page |
| Audit | Seed URL | Crawl (+ PSI / GSC if configured) | Score, issues, report |
| GSC | Connected `account_id` | Google Search Console | Sites, queries, CTR, position |

Credentials live in **`SEO-Agent/.env`** only (not `hermes-agent/.env`). Restart `seo-api` (and Hermes) after changing env.

---

### Confirm each integration quickly

| Integration | Check | Healthy signal |
|-------------|-------|----------------|
| PageSpeed | `GET /pagespeed/status` then `GET /pagespeed?url=https://example.com` | `configured: true`; later `status: ok` + lab score |
| Keywords + Labs | `GET /keywords/status` then `GET /keywords/research?keywords=seo%20audit` | `is_real_research: true`, `keyword_difficulty` present, `related` array |
| Labs only | `GET /keywords/difficulty?keywords=seo%20audit` / `GET /keywords/related?keyword=seo%20audit` | `status: ok` |
| GSC | `GET /auth/google/status?account_id=demo` then `/gsc/sites` | Connected; sites non-empty only after property verify |

---

### Changelog (append when a task finishes)

| Date | Done |
|------|------|
| 2026-08-06 | GSC Connect Google + basic client (verify postponed) |
| 2026-08-06 | PageSpeed Insights wired (API + audit + Hermes `check_pagespeed`) |
| 2026-08-06 | DataForSEO Keywords Data wired (API + Hermes `research_keywords`) |
| 2026-08-06 | DataForSEO Labs wired (difficulty + related; enrich research) |
| 2026-08-06 | Fix: SEO settings always load `SEO-Agent/.env` (Hermes cwd was missing keys) |
| 2026-08-06 | Hermes: set `tools.tool_search.enabled: off` so `research_keywords` is not deferred |
| 2026-08-07 | Hermes smoke passed: research_keywords + check_pagespeed + audit_site |
| 2026-08-07 | Hermes/in-process smoke: `keyword_plan` OK |
| 2026-08-07 | FastAPI `SEO_API_KEY` auth (Bearer / X-API-Key; off when unset) |
| 2026-08-07 | GSC → recommendations (page-2 + low CTR → actions; Hermes `gsc_account_id`) |
| 2026-08-08 | Hermes `gsc_status` / `gsc_sites` / `gsc_performance` + `auth_headers` parity |
| 2026-08-08 | Phase 2: SERP / rank / backlinks (DataForSEO; opt-in tools + audit flags) |
| — | *(next)* Owner validate Phase 3 before building |
