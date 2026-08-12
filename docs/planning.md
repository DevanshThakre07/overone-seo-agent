# SEO-Agent — Planning & Roadmap (living)

> **How to use this file**  
> - After every completed task: move it to **Completed**, update dates, and adjust **Next up**.  
> - Do **not** start a new phase until the owner validates the further-actions plan below.  
> - Keep secrets out of this file (no cookies, API keys, passwords).  
> - Companion status notes also live in `docs/GOOGLE_SEARCH_CONSOLE.md` (integrations detail).  
> - **Two tracks:** **SEO-strong** (priority now) vs **Fast path** (sellable product — kept, starts after SEO-strong gate). Near-term / Future / Capability map stay the full roadmap.  
> - **IDs to remember:** **S1–S4** = SEO-strong slices; **FP-1–FP-6** = Fast path slices — see **Glossary (S1 / S2 / …)** below.  
> - Last updated: **2026-08-12** (Module Response Quality P2 — GSC label honesty, alerts last-fire, keyword caller-only)

---

## Product goal

Build a **production-grade SEO agent** that can:

1. Access real sites (public **and** authenticated)  
2. Audit technical + on-page SEO  
3. Pull live search data (GSC, keywords, SERP, backlinks)  
4. Recommend concrete fixes (and later optionally apply them)  
5. Track progress over time and deliver client-ready reports  
6. Run via **CLI / FastAPI / Hermes** for the same engine  

**North star loop**

```text
Discover → Audit → Keywords → Rank/SERP → GSC gaps → Content advice
     → Tech/CWV → Backlinks → Track over time → Report → (optional) Apply
```

---

## Validation gate

| Question | Owner answer |
|----------|----------------|
| Approve Phase 1 (authenticated crawl v1 — cookie/header)? | ✅ **Validated 2026-08-07** |
| Approve overall phase order (1 → 2 → 3 → 4)? | ✅ Validated |
| **Agent quality before Phase 2?** | ✅ **Validated 2026-08-08** — fix trust/delivery first |
| **Approve Phase 2 (Competitive SEO)?** | ✅ **Validated 2026-08-08** — **1B + 2A** |
| **Approve Phase 3 (Retainer / product)?** | ✅ **Validated 2026-08-08** — **v1 without GA4** |
| **Approve Phase 4A (infra)?** | ✅ **Validated 2026-08-08** — **Postgres + job queue; SQLite fallback** |
| **Approve next after 4A?** | ✅ **Validated 2026-08-08** — **F (4A harden)** then **A (GA4)** |
| **Approve Fast path (sellable MVP)?** | ✅ **Validated 2026-08-10** — section kept; **starts after SEO-strong gate** |
| **Approve SEO-strong first?** | ✅ **Validated 2026-08-10** — trust → signals → depth (links/schema); fund SERP; defer full login / GEO / Apply / Local / product |

**Phase 4A owner constraints (enforced)**
1. Postgres + durable job queue; SQLite remains default for local/dev.  
2. Defer apply-suggestions, local SEO, GEO (OAuth Production was next after GA4).  
3. Infra first — then feature phases with validate.

**Phase 4A-F (harden)** ✅ shipped · **Phase A (GA4)** ✅ shipped · **Phase B (OAuth Production)** ✅ code/docs shipped (Cloud Publish remains owner step).

**Rule:** After each phase, re-validate the next phase before building.

---

## Completed (shipped)

| When | Item | Notes |
|------|------|--------|
| — | **Core engine** | Crawl → extract → analyzers → score → Markdown/JSON report → SQLite history |
| — | **Hermes plugin** | `integrations/hermes/seo_agent_plugin` — audit, optimize advice, keyword plan, etc. |
| — | **LLM optimize / keyword placement** | Suggestions only — does **not** edit live site or codebase; needs `OPENAI_API_KEY` |
| 2026-08-06 | **GSC Connect Google** | OAuth Web client, tokens per `account_id`, `/gsc/sites`, `/gsc/performance` |
| 2026-08-06 | **PageSpeed Insights** | API key; CWV on audit seed URL; Hermes `check_pagespeed` |
| 2026-08-06 | **DataForSEO Keywords Data** | Volume, CPC, competition; Hermes `research_keywords` |
| 2026-08-06 | **DataForSEO Labs** | Difficulty + related; enrich research endpoints |
| 2026-08-06 | **Settings `.env` path fix** | Always load `SEO-Agent/.env` (Hermes cwd-safe) |
| 2026-08-06 | **Hermes tool_search off** | SEO tools not deferred behind tool search |
| 2026-08-07 | **Hermes smokes** | `research_keywords`, `check_pagespeed`, `audit_site`, `keyword_plan` |
| 2026-08-07 | **API auth** | `SEO_API_KEY` → Bearer / `X-API-Key`; off when unset |
| 2026-08-07 | **GSC → recommendations** | Page-2 + low-CTR → `gsc_page2_opportunity` / `gsc_low_ctr`; Hermes `gsc_account_id` |
| 2026-08-07 | **GSC live account** | Connected as domain Gmail; property `sc-domain:bookasto.com` |
| 2026-08-07 | **Authenticated crawl v1** | Cookie/header on GET/HEAD; in-memory only; `check_login_wall` dry-run; `use_authenticated_crawl` opt-in |
| 2026-08-08 | **Agent quality (partial)** | Real sitemap analyzer; PSI/GSC report sections; Hermes executive_summary + smarter report truncate |
| 2026-08-08 | **Phase 1.5 Agent quality** | Hermes GSC tools + auth_headers; real robots.txt; stronger canonical/indexability; quieter schema + external links |
| 2026-08-08 | **Phase 2 Competitive SEO** | DataForSEO SERP + rank + backlinks; Hermes/API tools; opt-in audit flags `include_serp` / `include_backlinks` |
| 2026-08-08 | **Phase 3 v1 Retainer** | Trends, scheduled audits, dashboard UI/API, public share links; GA4 deferred |
| 2026-08-08 | **Phase 4A Infra** | Optional Postgres (`SEO_DATABASE_URL`); durable `/jobs` queue; SQLite fallback |
| 2026-08-08 | **Phase 4A-F Harden** | Postgres schedules/shares; due schedules → durable `/jobs`; finalize on complete |
| 2026-08-08 | **Phase A GA4** | Connect Google + `analytics.readonly`; `/ga4/*` + Hermes tools |
| 2026-08-08 | **Phase B OAuth Production** | Checklist API, env flags, `/legal/privacy`, Testing UX; Cloud Publish = owner |
| 2026-08-09 | **Phase G GA4 picker** | Preferred property per `account_id`; dashboard dropdown; audit omits id |
| 2026-08-10 | **Phase Rank history** | `rank_snapshots` SQLite/Postgres; dual-write audit SERP + `/rank`; API/dashboard/Hermes |
| 2026-08-10 | **Phase Schedule alerts** | Webhook on score drop / new criticals after compare audits; `GET /alerts/status`, `POST /alerts/test` |
| 2026-08-10 | **S1 Report trust** | Shared `signal_trust`; MD/PDF always stub skipped/not-run; PDF provisional score |
| 2026-08-10 | **S2 Signal completeness** | PDF/dashboard list parity for GSC/GA4/PSI/SERP/backlinks/keywords; optimize headings/FAQ |
| 2026-08-10 | **S3 Analyzer depth** | Crawl-scoped internal link graph (orphans/hubs/dead-ends); richer schema parse + homepage Organization/WebSite + required-field checks |
| 2026-08-10 | **FP-2 Host packaging** | Dockerfile + compose + `docs/HOSTING.md` + `PORT` env; owner still deploys to cloud |
| 2026-08-12 | **Plan Perfect PP-0→PP-8** | Truth defaults, schedules UI, analyzer drill-down, keywords/rank UX, schema advisor, GA4 narrative, rec accuracy fixtures (`tests/fixtures/rec_accuracy` + unit tests). PP-5 anchors wait on DataForSEO funds; PP-H owner host/OAuth |
| 2026-08-12 | **FP-4 Thin client scorecard** | Public `/share/{token}` HTML scorecard (score + top issues + rec peek + PDF); dashboard **Create client scorecard link**; README/allinfo contributor-facing |
| 2026-08-12 | **Module Response Quality (P0)** | Provisional score labeled on dashboard + scorecard; SERP aggregate not “ok” on total failure; rank errors ≠ “not ranking”; trends since-previous vs window span; dashboard keeps recommendation evidence; `_filled` blanks payment/missing_scope/etc. |
| 2026-08-12 | **Module Response Quality (P1)** | PageSpeed field/origin CrUX chips; login wall / auth crawl / rendering dedicated panels; compare shows score_delta + new/resolved; tools catalog `has_data` from real counts |
| 2026-08-12 | **Module Response Quality (P2)** | GSC listed-query totals labeled (not site-wide); alerts `last` fire/delivery in status + schedules UI; caller keywords shown without fake volume |

### What “optimize” means today (explicit)

- `optimize_page` / audit `optimize=true` → **advice only** (rewritten title/meta/H1, etc.)  
- Does **not** repair or patch the client’s codebase or CMS  
- Can use the same auth opt-in as crawl when fetching a logged-in page  

### Known limits of current product

- Auth crawl is **cookie/header only** (no Playwright form login / no POST)  
- GSC opportunities need enough impressions; new/low-traffic sites may return `opportunity_count: 0`  
- Point-in-time SERP/backlinks on audit; **rank history** snapshots persist across checks  
- GA4 v1 is separate endpoints/tools (not auto on every audit); older Google connections need re-consent  
- Dashboard v1 is static HTML over saved audits (no GA4 panel redesign yet)  
- PDF needs `pip install 'seo-agent[pdf]'` (fpdf2)  

- Google OAuth Cloud publish / verification is **owner-owned**; set `GSC_OAUTH_PUBLISHING_STATUS=production` after Publish  


---

## Capability map — toward “best in class”

Legend: ✅ done · 🔶 partial · ❌ missing

### A. Access & crawl
| Capability | Status | Notes |
|------------|--------|--------|
| Public HTTP crawl | ✅ | |
| Playwright JS render | 🔶 | Optional; SPA shells |
| Sitemap-first discovery | 🔶 | Improve coverage |
| **Authenticated crawl (cookie/header)** | ✅ | GET/HEAD + opt-in; see Phase 1 constraints |
| Playwright username/password login | ❌ | Deferred (cookie-only Phase 1; no form POST) |
| Scraper proxy (anti-bot) | ❌ | Optional later |
| Multi-page PageSpeed | 🔶 | Seed only today |

### B. Rankings & search data
| Capability | Status | Notes |
|------------|--------|--------|
| GSC Connect + performance | ✅ | |
| GSC → recommendations | ✅ | |
| Keyword volume / CPC / KD / related | ✅ | DataForSEO |
| SERP top results | ✅ | DataForSEO live/regular; opt-in tools + `include_serp` |
| Rank tracking over time | ✅ | `rank_snapshots`; `GET /rank/history`; dashboard + Hermes |
| Index coverage / sitemap API depth | 🔶 | robots.txt + sitemap analyzers real; GSC index API deferred |

### C. Off-page
| Capability | Status | Notes |
|------------|--------|--------|
| Backlink profile | ✅ | Summary + top referring domains (opt-in) |
| Toxic / risk links | ❌ | Phase 2+ |
| Brand mention monitoring | ❌ | Optional later |

### D. Content & on-page
| Capability | Status | Notes |
|------------|--------|--------|
| Technical + on-page analyzers | ✅ | |
| Prescriptive recommendations | ✅ | |
| LLM rewrite suggestions | ✅ | Advice only |
| Keyword placement plan | ✅ | |
| Content briefs from SERP | ❌ | Phase 2–3 |
| Internal linking graph | ✅ | Crawl-scoped orphans / dead-ends / hub concentration + metrics |
| Rich schema validation | ✅ | Parse errors; homepage Organization/WebSite; empty required fields; coverage |

### E. Local / international / GEO
| Capability | Status | Notes |
|------------|--------|--------|
| Local SEO (GBP, NAP) | ❌ | Phase 4 / separate |
| Hreflang / multi-locale | ❌ | Phase 4 |
| GEO / AI citations | ❌ | **Kept on roadmap** (owner 2026-08-09) — not started; validate before build |

### F. Analytics & outcomes
| Capability | Status | Notes |
|------------|--------|--------|
| GA4 traffic / conversions | 🔶 | Properties + report + preferred property picker; funnels later |
| CrUX standalone | ❌ | Low (PSI has field data) |
| Scheduled audits + trends | ✅ | `/trends` + interval schedules in seo-api |
| Monitoring alerts (webhook) | 🔶 | Engine ✅ (`AlertService` + `/alerts/*`); **Slack/Discord/webhook URL setup deferred** — leave unset until later |

### G. Delivery & product UX
| Capability | Status | Notes |
|------------|--------|--------|
| CLI + FastAPI + Hermes | ✅ | |
| Client dashboard | ✅ | `/dashboard` + `/dashboard/ui` v1 |
| PDF / shareable reports | ✅ | Share HTML + `?format=pdf`; `seo-agent[pdf]` / fpdf2 |
| Multi-tenant roles | ❌ | Phase 4 |
| Apply fixes (CMS / Git PR) | ❌ | Phase 4 (opt-in) |

### H. Production infrastructure
| Capability | Status | Notes |
|------------|--------|--------|
| `SEO_API_KEY` | ✅ | |
| OAuth Production + verification | 🔶 | Code/docs ✅; owner Publishes in Google Cloud |
| Postgres + job queue | ✅ | 4A: optional `SEO_DATABASE_URL`; SQLite default |
| Crawl auth secrets | ✅ | In-memory per request only (no disk/DB/logs) |
| Rate limits, audit logs, billing | ❌ | Phase 4 |
| Hosted HTTPS deploy | 🔶 | FP-2: Dockerfile + compose + `docs/HOSTING.md`; owner deploys to Railway/Render/Fly/VPS |

**Rough maturity:** strong on **tech + on-page + GSC + keywords + advice**; weak on **auth crawl, SERP, backlinks, rank track, dashboard, apply, multi-tenant infra**.

---

## Further actions

### Phase 1.5 — Agent quality ✅ *(validated 2026-08-08 — shipped)*

Make every signal **real**, scored fairly, and **shown clearly** before adding SERP/backlinks.

| # | Task | Status |
|---|------|--------|
| 1 | Real sitemap fetch (robots + `/sitemap.xml`) — kill stub `sitemap_not_checked` | ✅ |
| 2 | Report first-class **PageSpeed** + **GSC** sections; fix alt recount in overview | ✅ |
| 3 | Hermes: smarter report truncation; `audit_site` `executive_summary` (CWV sorted first) | ✅ |
| 4 | Hermes GSC tools + `auth_headers` parity | ✅ |
| 5 | Real robots.txt analyzer + stronger canonical/indexability | ✅ |
| 6 | Reduce external-link / schema noise | ✅ |

### Phase 1 — Authenticated crawl ✅ *(validated + shipped 2026-08-07)*

#### Hard constraints (owner-validated) — enforced
1. **Read-only crawl** — HTTP **GET/HEAD only**. No form POST login automation.  
2. **Credential storage** — In-memory per request only; never disk/DB/logs/reports.  
3. **Login-wall dry-run + opt-in** — `check_login_wall` / probe without creds; crawl uses creds only if `use_authenticated_crawl=true`.

#### Shipped
1. ✅ `auth_cookie` / `auth_headers` + `use_authenticated_crawl` on audit / optimize / keyword_plan  
2. ✅ `check_login_wall` + `GET /crawl/login-wall`  
3. ✅ HTTP + Playwright extra headers when opted in  
4. ✅ Redacted `summary.crawl_auth`  
5. ✅ Hermes + tests  

#### Auth UX flow
```text
check_login_wall(url)  →  { requires_login, signals, message }
        ↓ user opts in
audit(..., auth_cookie=..., use_authenticated_crawl=true)
        → GET/HEAD only with Cookie header (memory only)
```

### Phase 2 — Competitive SEO ✅ *(validated 2026-08-08 — 1B+2A — shipped)*

| # | Task | Status |
|---|------|--------|
| 1 | DataForSEO **SERP** (top organic results) — tool + API + Hermes | ✅ |
| 2 | Simple **rank check** (domain position for keywords) | ✅ |
| 3 | DataForSEO **Backlinks** (summary + top referring domains) | ✅ |
| 4 | Optional audit flags `include_serp` / `include_backlinks` (+ keywords) | ✅ |
| — | Deeper GSC index/sitemap API | ⏸ deferred |

Constraints: never auto-enrich audits; paid calls only when explicitly requested.

### Phase 3 — Retainer / product surface ✅ *(validated 2026-08-08 — v1 shipped)*

| # | Task | Status |
|---|------|--------|
| 1 | Score/issue **trends** from history (`GET /trends`, Hermes) | ✅ |
| 2 | **Scheduled audits** (interval, SQLite + background runner) | ✅ |
| 3 | Customer **dashboard** v1 (static + aggregate API) | ✅ |
| 4 | Report **share links** (public token view) | ✅ |
| — | GA4 enrichment | ✅ v1 shipped (endpoints + Hermes); audit flag / funnels later |
| — | Polished PDF | ⏸ stretch / later |

### Phase 4 — Scale, apply, expand

#### Phase 4A — Infra ✅ *(validated + shipped 2026-08-08)*
| # | Task | Status |
|---|------|--------|
| 1 | Optional Postgres via `SEO_DATABASE_URL` / `DATABASE_URL` | ✅ |
| 2 | Durable job queue (same backend; SQLite fallback) | ✅ |
| 3 | Keep `POST /audit?background=true` + `GET /jobs/{id}` compatible | ✅ |
| 4 | SQLite remains default local/dev | ✅ |

#### Deferred from 4A — further steps (awaiting owner validate)
Do **not** start these until the owner picks one. Same defer list as Phase 4A constraints.

| Option | Item | Why deferred / notes | Status |
|--------|------|----------------------|--------|
| **A** | **GA4** enrichment (was 3.5) | Extra OAuth scopes + analytics surface | ✅ v1 shipped |
| **B** | Google **OAuth Production** publish | Owner-owned Google Cloud / verification; product checklist + UX | ✅ code/docs shipped |
| **C** | **Apply suggestions** (CMS / Git PR) | High risk — needs hard consent rules before build | ⏸ awaiting validate |
| **D** | **Local SEO** / hreflang | Product expand, not infra | ⏸ awaiting validate |
| **E** | **GEO** / AI citations | **Keep on roadmap** — separate product slice; do not drop | ⏸ planned (awaiting validate to start) |
| **F** | 4A harden only | Postgres schedules/shares, schedule → `/jobs`, more tests — no new feature | ✅ shipped |
| **G** | **GA4 property picker** (UX) | Save preferred property by name; audits omit id | ✅ shipped |
| **PDF** | Branded downloadable report | Extends share/report loop | ✅ shipped |

Also stretch (done): polished **PDF** ✅.

#### Phase E — GEO / Generative Engine Optimization *(planned — do not remove)*
Owner confirmed **keep GEO in planning**. Build only after explicit validate.

| # | Direction (draft — refine at validate) | Status |
|---|----------------------------------------|--------|
| 1 | Visibility in AI answers / citations (ChatGPT, Perplexity, Google AI Overviews, etc.) | ⏸ planned |
| 2 | Content & entity signals that help generative engines cite the site | ⏸ planned |
| 3 | Opt-in tools + report section (same pattern as SERP/GA4 — never auto-bill) | ⏸ planned |
| — | Start build | ⏸ awaiting owner validate |

#### Phase 4A-F — Harden ✅ *(validated + shipped 2026-08-08)*
| # | Task | Status |
|---|------|--------|
| 1 | Postgres schedule + share repositories (SQLite fallback) | ✅ |
| 2 | Schedules enqueue durable `/jobs` + finalize on complete/fail | ✅ |
| 3 | Factory wire + tests | ✅ |

#### Phase A — GA4 ✅ *(validated + shipped 2026-08-08)*
| # | Task | Status |
|---|------|--------|
| 1 | Add `analytics.readonly` to Connect Google scopes + re-consent messaging | ✅ |
| 2 | `/ga4/status`, `/ga4/properties`, `/ga4/report` (REST, reuse tokens) | ✅ |
| 3 | Hermes `ga4_status` / `ga4_properties` / `ga4_report` | ✅ |
| 4 | Audit `include_ga4` + `ga4_property_id` → `summary.google_analytics` | ✅ |
| 5 | Dashboard GA4 panel + markdown report section | ✅ |
| — | Funnel weighting into recommendations | ⏸ later |

#### Phase B — OAuth Production ✅ *(validated + code/docs shipped 2026-08-08)*
| # | Task | Status |
|---|------|--------|
| 1 | Owner checklist `GET /auth/google/production` + `production_checklist` helper | ✅ |
| 2 | Env: `GSC_OAUTH_PUBLISHING_STATUS`, `GSC_PRIVACY_POLICY_URL`, `GSC_HOMEPAGE_URL` | ✅ |
| 3 | Status/Connect UX: Testing vs Production messaging; `access_denied` HTML hint | ✅ |
| 4 | Public privacy stub `GET /legal/privacy` (for consent screen URL) | ✅ |
| 5 | Docs: Production publish checklist in `GOOGLE_SEARCH_CONSOLE.md` | ✅ |
| — | **Owner:** Publish consent screen in Google Cloud + verification + set env | ⏸ owner |

#### Phase G — GA4 property picker ✅ *(validated + shipped 2026-08-09)*
| # | Task | Status |
|---|------|--------|
| 1 | Persist `preferred_ga4_property_id` on Connect Google `account_id` | ✅ |
| 2 | `GET/PUT /ga4/preference` + list_properties returns preferred | ✅ |
| 3 | Audit `include_ga4` uses saved preference when `ga4_property_id` omitted | ✅ |
| 4 | Dashboard dropdown by display name + “Save GA4 default” | ✅ |
| 5 | Hermes `ga4_set_preference` + report/audit optional property_id | ✅ |
| 6 | Dashboard polish: GSC match-vs-URL warning; collapse blank opt-in panels | ✅ |

#### Phase PDF — Downloadable report ✅ *(validated + shipped 2026-08-09)*
| # | Task | Status |
|---|------|--------|
| 1 | Optional `seo-agent[pdf]` (fpdf2) + clear missing-dep error | ✅ |
| 2 | `render_pdf` branded report (score, issues, recs, PSI/GSC/GA4) | ✅ |
| 3 | Binary-safe API: `GET/POST /report` PDF + `Content-Disposition` | ✅ |
| 4 | Share `?format=pdf` + HTML Download PDF link | ✅ |
| 5 | CLI / Hermes path delivery (no base64 in chat) | ✅ |

---

## Near-term — strengthen SEO *(before monetize UX)*

Work the engine and truthful delivery — not marketing chrome / narrative dashboard clone.

> **Priority (validated 2026-08-10):** finish **SEO-strong** below before executing Fast path FP-2+ (host/Stripe). Fast path section stays documented but deferred.

### SEO-strong order *(validated 2026-08-10)*

| # | Focus | Status | Notes |
|---|--------|--------|-------|
| S1 | **Report trust** — Markdown + PDF parity; clear skipped / not-run wording | ✅ shipped 2026-08-10 | Soft: trust/polish |
| S2 | **Signal completeness** — GA4/SERP/backlinks/optimize/PSI consistently on dashboard + PDF when run | ✅ shipped 2026-08-10 | Soft: incomplete delivery |
| S3 | **Analyzer depth** — internal linking graph + richer schema validation | ✅ shipped 2026-08-10 | Soft: thin depth |
| S4 | **DataForSEO funded** — owner tops up SERP so rank history / live SERP stop looking empty | ✅ smoke 2026-08-10 | Tiny keyword OK; avoid heavy SERP until more $ |
| — | Rank history | ✅ shipped 2026-08-10 | |
| — | Schedule alerts engine | ✅ shipped 2026-08-10 — channel setup later | |

### Glossary — what S1 / S2 / S3 / S4 mean *(read this later)*

Plain-English cheat sheet so “S1 Report trust” still makes sense months from now. **S** = SEO-strong. **FP** = Fast path (sellable product). Same number does **not** mean the same work across tracks except **S1 = FP-1**.

| ID | Name | In one sentence | Problem it fixes | Done when… | Key code / notes |
|----|------|-----------------|------------------|------------|------------------|
| **S1** | **Report trust** | Reports tell the truth about what was and wasn’t run. | MD/PDF used to **hide** skipped PageSpeed/GSC/GA4/SERP/backlinks/optimize — looked like those features didn’t exist. | Every major signal has a visible **Trust: Not run / OK / Error / Unavailable** stub in **Markdown and PDF**; provisional scores labeled on PDF too. | `app/reports/signal_trust.py`, `markdown_report.py`, `pdf_report.py` — ✅ shipped 2026-08-10 |
| **S2** | **Signal completeness** | When a signal **did** run, it shows up everywhere that matters. | Opt-in data sometimes lands in summary/API but not dashboard, PDF, or share — incomplete client delivery. | If audit flags `include_*` / optimize / PSI ran successfully, results appear on **dashboard + Markdown + PDF** (same facts, no silent drop). | PDF/MD/dashboard list parity for GSC/GA4/PSI/SERP/BL/keywords/optimize — ✅ shipped 2026-08-10 |
| **S3** | **Analyzer depth** | Core on-site SEO analysis gets stronger (not more chrome). | Internal links + schema checks are thin vs best-in-class auditors. | Richer **internal linking graph** findings + deeper **schema** validation/issues in audit score + reports. | `links_analyzer` graph + `schema_analyzer` / extractor JSON-LD blocks — ✅ shipped 2026-08-10 |
| **S4** | **DataForSEO funded** | Live SERP/rank history actually has data (owner money, not code). | Rank history / SERP look “empty” when DataForSEO returns Payment Required. | Account has SERP balance; a real `/rank` or `include_serp` audit writes snapshots. | Owner tops up DataForSEO — not a build sprint |
| **Rank history** | (shipped) | Store keyword positions over time. | Point-in-time SERP only — couldn’t answer “are we moving?” | `rank_snapshots` + `GET /rank/history` + dashboard panel. | ✅ 2026-08-10 |
| **Schedule alerts** | (engine shipped) | Fire webhook when score drops / new criticals after compare. | Schedules ran but nobody got notified. | Engine + `/alerts/*` live; **Slack/channel URL setup later**. | ✅ engine; channels deferred |

#### S1 vs S2 (easy to confuse)

| | **S1 Report trust** | **S2 Signal completeness** |
|--|---------------------|----------------------------|
| Focus | Honesty when something was **skipped** | Completeness when something **ran** |
| Bad before | Silent omit → “feature missing?” | Ran SERP but PDF/dashboard blank |
| Good after | “Trust: **Not run** — pass include_serp…” | SERP block filled on dashboard **and** PDF |

#### Fast path IDs (after SEO-strong gate)

| ID | Name | In one sentence |
|----|------|-----------------|
| **FP-1** | Report trust | Same as **S1** (already shipped). |
| **FP-2** | Host | Put `seo-api` on HTTPS with secrets + storage. |
| **FP-3** | OAuth Production | Google Cloud Publish so clients can Connect Google outside Testing. |
| **FP-4** | Thin client delivery | One flow: audit → scorecard → PDF (no heyfixit clone). |
| **FP-5** | Billing | Stripe Checkout so clients can pay online. |
| **FP-6** | Client isolation | Per-client `account_id` / API key boundaries. |

#### Other labels you’ll see

| Label | Meaning |
|-------|---------|
| **SEO-strong gate** | S1–S3 done (S4 funded ideally) → then start Fast path FP-2+. |
| **Near-term** | Broader strengthen-SEO list; S1–S4 is the ordered cut of it. |
| **Future / parked** | GEO, Apply, Local, Slack channels, narrative dashboard — not now. |
| **Validate** | Owner must approve the next slice before we build it. |

### Explicitly deferred while SEO-strong runs

| Item | Why deferred |
|------|----------------|
| Playwright full login automation | Cookies cover most agency cases; high cost / low near-term ROI |
| GEO (E) / Apply (C) / Local (D) | New product surfaces — keep on Future; validate later |
| Toxic-link scoring | Optional after S3; not required for “strong” gate |
| Host / Stripe / multi-client packaging | **Fast path** — after SEO-strong gate |
| Slack / alert channels | Later (already parked) |

```text
S1 Report trust → S2 Signal completeness → S3 Links + schema depth
     (+ S4 owner: fund DataForSEO in parallel)
     → then Fast path FP-2+ (Host → OAuth → thin client → Stripe → isolation)
```

### Near-term checklist (legacy rows — kept)

| # | Focus | Status |
|---|--------|--------|
| 1 | Signal completeness on saved audits (GA4/SERP/backlinks/optimize/PSI → dashboard + PDF) | ✅ = **S2 shipped** |
| 2 | **Rank history** — persist SERP/rank snapshots over time (“are we moving?”) | ✅ shipped 2026-08-10 |
| 3 | Schedule **alerts** — score drop / new criticals (webhook first; email later) | ✅ engine shipped 2026-08-10 — **channel setup later** |
| 4 | Report trust — Markdown + PDF parity; clear skipped/not-run wording | ✅ = **S1 shipped** |
| — | Do **not** clone heyfixit-style Overview/Auditor/Spy/Diagnoser/Fixer tabs yet | parked → production |

---

## Future — production / monetize *(parked — do not start until production stage)*

Owner (2026-08-10): strengthen SEO first; client-narrative dashboard and monetization packaging wait until **hosting + OAuth Production + billing readiness**. Then validate a **Phase Monetize** slice before build.

> **Note:** Fast path is the sellable cut of this section. **SEO-strong runs first** (validated 2026-08-10). Items out of both SEO-strong and Fast path stay parked (GEO, Apply, Local, heyfixit UI, Slack channels, etc.). See **Glossary** above for S/FP IDs.

| Item | Notes | Status |
|------|--------|--------|
| Client delivery UX | Scorecard + Audit / Diagnose / Fix / Track tabs (real data only; blank when missing) | ⏸ production |
| **Alert channels** | Wire `SEO_ALERT_WEBHOOK_URL` (Slack / Discord / custom) + dry-run; optional email after | ⏸ **later** (owner 2026-08-10 — skip Slack/workspace for now) |
| Monitoring alerts (productized) | Multi-channel packaging / client-facing alert prefs | ⏸ production |
| Multi-client isolation | API keys / account_id boundaries for multiple clients | ⏸ production |
| Share + PDF retainer handoff polish | Already shipped basics; packaging for paid clients | ⏸ production |
| **GEO (E)** | AI citations / generative visibility — keep on roadmap; validate before build | ⏸ planned |
| **Apply (C)** | CMS / Git PR / paste packs — hard consent rules first | ⏸ awaiting validate |
| Billing / SaaS self-serve | After agency delivery path is solid | ⏸ production |

**Explicitly not next:** clone [vibha demo dashboard](https://vibha-ramprakash.github.io/seo-geo-tracker/dashboard.html); AI-Search Spy; Fixer paste-pack CMS apply.

```text
SEO-strong (S1–S3 + fund SERP) → Fast path (Host + OAuth + Stripe) → deeper Future items
```

---

## Fast path — sellable product *(validated 2026-08-10; deferred until SEO-strong gate)*

**Goal:** clients can **pay online** and get value — not finish the entire capability map.

**Definition of done (buyable MVP):**

```text
Pay → Connect Google → Run audit → Dashboard scorecard → Download / share PDF
```

**Relationship to other sections:** Near-term + Future + Capability map stay the long-term truth. Fast path stays documented. **Do not start FP-2+ until SEO-strong S1–S3 are done** (owner 2026-08-10). FP-1 (report trust) = SEO-strong S1 — build once, counts for both.

### In scope (ordered)

| # | Slice | What ships | Status |
|---|--------|------------|--------|
| FP-1 | **Report trust** | Markdown + PDF parity; clear skipped / not-run wording | ✅ = SEO-strong **S1** shipped 2026-08-10 |
| FP-2 | **Host** | HTTPS deploy of `seo-api` + storage + secrets (owner picks host) | ✅ packaging 2026-08-10 — owner deploys |
| FP-3 | **OAuth Production** | Google Cloud Publish + env (`GSC_OAUTH_PUBLISHING_STATUS=production`) — mostly owner | ⏸ after SEO-strong (code/docs ✅) |
| FP-4 | **Thin client delivery** | One flow: audit → scorecard → PDF share (reuse dashboard/share; **no** Spy/Fixer/heyfixit clone) | ✅ 2026-08-12 (`/share/{token}` scorecard + dashboard create link) |
| FP-5 | **Billing** | Stripe Checkout — one plan / per-site (or simple retainer SKU) | ⏸ after SEO-strong |
| FP-6 | **Client isolation** | Per-client `account_id` / API key boundaries (enough to sell; not full IAM) | ⏸ after SEO-strong |

### Explicitly out of Fast path *(keep on full roadmap)*

| Deferred | Where it lives |
|----------|----------------|
| Slack / Discord / webhook channel wiring | Future → Alert channels |
| Email alerts, productized monitoring prefs | Future |
| GEO (E), Apply (C), Local (D) | Future / planned |
| heyfixit-style Overview / Auditor / Spy / Diagnoser / Fixer | Future → Client delivery UX |
| Toxic links, content briefs, CrUX standalone | Capability map ❌ |
| Full multi-tenant roles, rate limits, audit-log billing depth | Future / H. Production |
| Hermes-as-primary UX | Keep Hermes for chat; sellable surface = hosted API + dashboard |
| Playwright full login | Deferred under SEO-strong |

### Fast path sequencing

```text
[SEO-strong S1–S3 first]
FP-1 Report trust (= S1) → FP-2 Host → FP-3 OAuth Publish (owner)
     → FP-4 Thin client flow → FP-5 Stripe → FP-6 Isolation harden
```

### Owner constraints (Fast path)

1. Do **not** build Slack workspace / alert channels for MVP.  
2. Do **not** clone narrative GEO-tracker dashboards.  
3. Prefer reuse of existing dashboard + PDF + Connect Google over new product chrome.  
4. Full planning sections remain authoritative for anything not listed In scope above.  
5. **SEO-strong before FP-2+** (validated 2026-08-10).

---

## Immediate next step

| Status | Action |
|--------|--------|
| **Active stage** | **Module Response Quality** — honest/complete responses per integrated module (HTTPS parked) |
| **Now (build)** | Module Response Quality P0–P2 shipped — HTTPS still parked |
| **Owner parallel** | When ready: deploy HTTPS → OAuth; fund DataForSEO (PP-5) |
| **Still deferred** | Form login; GEO; Apply; Local; Stripe; Slack workspace |

Do **not** create a Slack workspace for alerts now — leave `SEO_ALERT_WEBHOOK_URL` unset until the later channel-setup slice.

---

## How we update this file (checklist)

When a task finishes:

- [ ] Add a row under **Completed** with date  
- [ ] Flip status in **Capability map** (❌ → 🔶/✅)  
- [ ] Remove or check off the item under **Further actions**  
- [ ] Set **Immediate next step** to the new top item  
- [ ] If SEO-strong work: flip status in **SEO-strong order**  
- [ ] If Fast path work: flip status in **Fast path — In scope** (only after SEO-strong gate for FP-2+)  
- [ ] Bump **Last updated** at the top  
- [ ] Mirror critical status in `docs/GOOGLE_SEARCH_CONSOLE.md` when integrations change  

---

## Owner validation log

| Date | Decision |
|------|----------|
| 2026-08-07 | Phase 1 validated with adds: read-only GET, in-memory credentials only, login-wall dry-run + opt-in |
| 2026-08-08 | **Agent quality first** validated (before Phase 2) |
| 2026-08-08 | Phase 1.5 **shipped** — awaiting owner validate before Phase 2 |
| 2026-08-08 | **Phase 2 validated** — 1B (opt-in tools + audit flags) + 2A (SERP/rank/backlinks; defer GSC index) |
| 2026-08-08 | **Phase 3 validated** — v1 without GA4 (trends, schedules, dashboard, share links) |
| 2026-08-08 | Phase 3 v1 **shipped** — awaiting owner validate before Phase 4 / GA4 3.5 |
| 2026-08-08 | **Phase 4A validated** — Postgres + job queue; SQLite fallback; defer OAuth/apply/local/GEO/GA4 |
| 2026-08-08 | **Phase 4A shipped** — optional Postgres audits/jobs; durable queue; SQLite local/dev default |
| 2026-08-08 | **Next = F (4A harden)** — solidify infra before GA4/apply/local/GEO |
| 2026-08-08 | **Phase 4A-F shipped** — Postgres schedules/shares; schedules → `/jobs` |
| 2026-08-08 | **Phase A (GA4) validated + shipped** — after “go ahead” post 4A-F restart |
| 2026-08-08 | **Phase B (OAuth Production) validated** — “go ahead with b” |
| 2026-08-08 | **Phase B code/docs shipped** — Cloud Publish + verification remain owner steps |
| 2026-08-09 | Hermes kept for chat for now; SEO-Agent remains standalone for future web app |
| 2026-08-09 | OAuth Production deferred until product is hosted (Testing fine locally) |
| 2026-08-09 | **GEO (E) kept on roadmap** — planned future slice; do not drop; validate before build |
| 2026-08-09 | **Phase G (GA4 picker) validated** — “move ahead as the plan” (suggested next) |
| 2026-08-09 | **Phase G shipped** — preferred GA4 property per account_id; dashboard + API + Hermes |
| 2026-08-09 | **Phase PDF validated** — owner chose PDF for retainer delivery loop |
| 2026-08-09 | **Phase PDF shipped** — fpdf2 report; share/API/CLI/Hermes |
| 2026-08-10 | **Monetize / client-narrative dashboard deferred** until production (hosting + OAuth Production + billing readiness) |
| 2026-08-10 | **Near-term = strengthen SEO** — default next: **rank history**; then schedule alerts; GEO/Apply stay validate-gated |
| 2026-08-10 | **Rank history validated + shipped** — snapshots table; dual-write from audit SERP + `/rank`; `GET /rank/history`; dashboard + Hermes |
| 2026-08-10 | **Schedule alerts shipped** — webhook on score drop / new criticals; routes + job hook; email later |
| 2026-08-10 | **Alert channel setup deferred** — no Slack workspace now; wire webhook/email later |
| 2026-08-10 | **Fast path validated** — sellable MVP track added as its own section; Near-term / Future / Capability map **kept**; out of scope: Slack, GEO, Apply, heyfixit clone |
| 2026-08-10 | **SEO-strong first validated** — S1 report trust → S2 signals → S3 links/schema; fund DataForSEO (owner); defer full login / GEO / Apply / Local / product; Fast path FP-2+ after gate |
| 2026-08-10 | **S1 Report trust shipped** — `app/reports/signal_trust.py`; MD/PDF always show Trust/Not run stubs; PDF provisional score; tests |
| 2026-08-10 | **Glossary added** — plain-English S1–S4 + FP-1–FP-6 cheat sheet in Near-term (for later reading) |
| 2026-08-10 | **S2 Signal completeness shipped** — GSC/GA4 period+lists on PDF/dashboard; PSI INP/issues; SERP competitors; optimize FAQ/headings |
| 2026-08-10 | **S3 Analyzer depth shipped** — crawl-scoped link graph; schema parse errors + Organization/WebSite + required fields |
| 2026-08-10 | **Next order approved** — (1) smoke Actoro multi-page → dashboard + PDF · (2) fund DataForSEO · (3) FP-2 Host |
| 2026-08-10 | **Actoro smoke ✅** — audit `d44a8d4b-…` 3 pages JS-rendered; S3 graph metrics; dashboard + PDF; GSC/GA4 OK |
| 2026-08-10 | **S4 DataForSEO creds updated** — login OK, balance $1; **API blocked until account verification** (40104); no paid spend yet |
| 2026-08-10 | **S4 smoke ✅** — `search_volume(["actoro"])` → volume 390; ~$0.09 spent; balance ~$0.91; skip SERP/backlinks until more funds |
| 2026-08-10 | **Client-hurry pipeline** — deliver audit/PDF pack first; Host only if remote; defer form-login / Stripe / GEO |
| 2026-08-10 | **Actoro delivery pack ✅** — audit `a8d5c3f9-…` score 74 / 3 pages; PDF + 30-day share; no SERP (DFS $ low) |
| 2026-08-10 | **FP-2 Host packaging ✅** — `Dockerfile`, `docker-compose.yml`, `docs/HOSTING.md`, `PORT` env; owner deploys |
| 2026-08-10 | **FP-2 local Docker smoke ✅** — compose healthy; API key required; `/` redirects to dashboard |
| 2026-08-11 | **Full-project deploy wiring ✅** — root `docker-compose.yml` (seo-api + Hermes profile); `DEPLOY.md` |
| 2026-08-12 | **Plan Perfect validated** — owner: write full plan at bottom of planning.md and start process |

Next: owner **PP-H** + **PP-5** (DataForSEO funds). Plan Perfect code path complete; do not block on Stripe/SaaS.

---

## Plan Perfect — near-accurate, complete responses *(validated 2026-08-12)*

**Goal:** Every dashboard/API/PDF signal is **honest**, **actionable**, and **as accurate as the underlying data allows** — no silent empties, no misleading defaults, no “admin only” dead ends for core SEO loops.

**Definition of done (near-perfect, not infinite):**

```text
Crawl enough pages → score + issues that match reality
  → GSC/GA4 snapshots clear
  → Keywords with volume/CPC/related surfaced
  → Rank / history readable
  → Backlinks with risk (when funded)
  → Placement + optimize advice grounded in live page
  → Schedules assignable from dashboard
  → Analyzers drill into real issues
  → Empty/error states always explain why + what to do
```

**Non-goals (still Future / Fast path):** Stripe, multi-tenant IAM, form-login Playwright, GEO, Apply-to-CMS, Slack workspace, heyfixit clone.

**Accuracy rules (enforce on every PP slice)**

1. **Never invent metrics** — blank/error with reason beats fake numbers.  
2. **Recommendations must cite evidence** — page URL, field, current value, or GSC/GA4 row when available.  
3. **Paid calls stay opt-in** — SERP/backlinks never auto; show 402 as “fund DataForSEO,” not “feature broken.”  
4. **Defaults must not lie** — if dashboard Max pages=1, label it as quick scan; “full audit” needs higher default or explicit confirm.  
5. **Mobile PSI preferred** when PageSpeed runs (Google-weighted).  
6. **Update `docs/understand.md` + section `i` help** when behavior changes.

### Ordered slices

| ID | Slice | Ships | Status |
|----|--------|--------|--------|
| **PP-0** | **Truth defaults** | Dashboard Max pages default ↑ (e.g. 15); PageSpeed default **mobile** (or both when on); clearer quick-scan vs full-audit labeling; recommendation messages cite evidence; paid-error copy standardized | ✅ 2026-08-12 |
| **PP-1** | **Schedules UI** | Create / pause / delete / run-due from dashboard; panel stops being API-only | ✅ 2026-08-12 |
| **PP-2** | **Analyzer drill-down** | Analyzers panel expands to issue list (code + message + URL) — no duplicate-without-detail | ✅ 2026-08-12 |
| **PP-3** | **Keywords depth UI** | Surface CPC, competition, related/gap keywords already in API; short intent hint where reliable | ✅ 2026-08-12 |
| **PP-4** | **Rank UX** | Human labels for not-found vs position; history shows dates; optional single-keyword spotlight | ✅ 2026-08-12 |
| **PP-5** | **Backlinks depth** | Keep spam/risk; add anchors when DFS endpoint funded; graceful 402 UX | ⏸ owner funds (402 UX ✅) |
| **PP-6** | **Schema advisor** | Beyond “missing” — recommend Organization/WebSite/FAQ/Article/Product by page type + validate existing JSON-LD | ✅ 2026-08-12 |
| **PP-7** | **GA4 narrative lite** | Sessions → top pages → simple “so what” line (no fake revenue unless conversion data exists) | ✅ 2026-08-12 |
| **PP-8** | **Rec accuracy hardening** | Golden fixtures: Actoro + privacy + complete page; tests that recommendations don’t contradict page evidence | ✅ 2026-08-12 |
| **PP-H** | **Host / OAuth (owner)** | HTTPS deploy + Google Publish — parallel, not blocked by PP build | ⏸ owner |

```text
PP-0 Truth defaults → PP-1 Schedules UI → PP-2 Analyzer drill-down
  → PP-3 Keywords UI → PP-4 Rank UX → PP-5 Backlinks (funded)
  → PP-6 Schema advisor → PP-7 GA4 narrative → PP-8 Rec fixtures
  ‖ parallel: PP-H owner host + OAuth + DataForSEO balance
```

### PP-0 checklist (current)

| # | Task | Status |
|---|------|--------|
| 1 | Raise dashboard default `max_pages` + label quick vs full | ✅ |
| 2 | PageSpeed strategy default mobile when enabled | ✅ (`PAGESPEED_STRATEGY=mobile` + UI On—mobile) |
| 3 | Standardize DataForSEO 402 / skip messaging on dashboard | ✅ |
| 4 | Recommendations: require evidence fields in top issues/recs rendering | ✅ |
| 5 | Sync `understand.md` + `i` help for new defaults | ✅ |

### Owner dependencies

| Item | Why |
|------|-----|
| DataForSEO balance / verification | PP-5 backlinks + heavy SERP stay empty/402 without it |
| HTTPS + OAuth Publish | Real client Connect Google outside Testing |
| Alert webhook URL (later) | Optional; not required for PP-1 schedules |

### Explicitly still out of Plan Perfect

| Deferred | Where |
|----------|--------|
| Stripe / FP-5–6 SaaS | Fast path |
| Playwright form login | SEO-strong deferred |
| GEO / Apply / Local | Future |
| Slack workspace | Future alert channels |
| heyfixit UI clone | Future client delivery UX |
