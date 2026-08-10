# SEO-Agent — Planning & Roadmap (living)

> **How to use this file**  
> - After every completed task: move it to **Completed**, update dates, and adjust **Next up**.  
> - Do **not** start a new phase until the owner validates the further-actions plan below.  
> - Keep secrets out of this file (no cookies, API keys, passwords).  
> - Companion status notes also live in `docs/GOOGLE_SEARCH_CONSOLE.md` (integrations detail).  
> - Last updated: **2026-08-10** (Rank history shipped; alerts next; monetize UX parked)

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
| **Approve next after GA4?** | ✅ **Validated 2026-08-08** — **B (OAuth Production)** |

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
| Internal linking graph | 🔶 | Thin |
| Rich schema validation | 🔶 | Coverage aggregated (less noise); deep validation still thin |

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
| Hosted HTTPS deploy | ❌ | Phase 4 |

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

| # | Focus | Status |
|---|--------|--------|
| 1 | Signal completeness on saved audits (GA4/SERP/backlinks/optimize/PSI → dashboard + PDF) | 🔶 partial (optimize in PDF ✅; keep hardening) |
| 2 | **Rank history** — persist SERP/rank snapshots over time (“are we moving?”) | ✅ shipped 2026-08-10 |
| 3 | Schedule **alerts** — score drop / new criticals (webhook first; email later) | ⏸ **next to validate / build** |
| 4 | Report trust — Markdown + PDF parity; clear skipped/not-run wording | 🔶 ongoing |
| — | Do **not** clone heyfixit-style Overview/Auditor/Spy/Diagnoser/Fixer tabs yet | parked → production |

---

## Future — production / monetize *(parked — do not start until production stage)*

Owner (2026-08-10): strengthen SEO first; client-narrative dashboard and monetization packaging wait until **hosting + OAuth Production + billing readiness**. Then validate a **Phase Monetize** slice before build.

| Item | Notes | Status |
|------|--------|--------|
| Client delivery UX | Scorecard + Audit / Diagnose / Fix / Track tabs (real data only; blank when missing) | ⏸ production |
| Monitoring alerts (productized) | Score drop / new criticals after schedules — also listed near-term as SEO bridge | ⏸ / near-term webhook OK earlier |
| Multi-client isolation | API keys / account_id boundaries for multiple clients | ⏸ production |
| Share + PDF retainer handoff polish | Already shipped basics; packaging for paid clients | ⏸ production |
| **GEO (E)** | AI citations / generative visibility — keep on roadmap; validate before build | ⏸ planned |
| **Apply (C)** | CMS / Git PR / paste packs — hard consent rules first | ⏸ awaiting validate |
| Billing / SaaS self-serve | After agency delivery path is solid | ⏸ production |

**Explicitly not next:** clone [vibha demo dashboard](https://vibha-ramprakash.github.io/seo-geo-tracker/dashboard.html); AI-Search Spy; Fixer paste-pack CMS apply.

```text
Strengthen SEO engine → Rank history + schedule alerts → Host + OAuth Production → Monetize UX / billing
```

---

## Immediate next step

| Status | Action |
|--------|--------|
| **Now** | **Schedule alerts** (webhook on score drop / new criticals) — next SEO strengthen slice |
| **Shipped** | **Rank history** — `rank_snapshots` table; `GET /rank/history`; dashboard panel; Hermes `list_rank_history` |
| **Parked** | Client-narrative dashboard + Phase Monetize → **production stage** |
| **Kept planned** | **GEO (E)** / **Apply (C)** / **Local (D)** — validate before build |

Owner must validate **schedule alerts** before the next code build.

---

## How we update this file (checklist)

When a task finishes:

- [ ] Add a row under **Completed** with date  
- [ ] Flip status in **Capability map** (❌ → 🔶/✅)  
- [ ] Remove or check off the item under **Further actions**  
- [ ] Set **Immediate next step** to the new top item  
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

Re-validate next **code** build (**schedule alerts**) before implementing. **C** / **D** / **E** and Phase Monetize remain parked.
