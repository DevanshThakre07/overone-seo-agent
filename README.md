# AI SEO Agent

Standalone SEO engine: **crawl → extract → analyze → score → recommend**, with optional Google Search Console, GA4, PageSpeed, and DataForSEO enrichment.

Primary surfaces for contributors:

- **Dashboard** — `http://localhost:8000/dashboard/ui`
- **HTTP API** — OpenAPI at `/docs`
- **CLI** — `seo-audit`, `seo-optimize`, `seo-report`, …

Deep dive for contributors: **[`allinfo.md`](allinfo.md)**  
Dashboard beginner labels: [`docs/understand.md`](docs/understand.md)  
Hosting: [`docs/HOSTING.md`](docs/HOSTING.md)

---

## Architecture

```text
Dashboard / CLI / HTTP API
        ↓
   tools/ + services/   (SeoService orchestration)
        ↓
 crawler → extractor → analyzers → score + recommendations
        ↓
 SQLite or Postgres · reports (MD / PDF) · public share scorecard
```

Each SEO check is a plugin under `app/analyzers/`, run by `AnalyzerRegistry`.

**Optimize / recommendations are advice only** — this agent does not edit the customer’s live site.

---

## Quick start

Requires **Python 3.11+** (3.12 recommended).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # add keys locally — never commit .env

seo-audit https://example.com -o out.json --max-pages 10
# or
python -m app.main https://example.com -o out.json --max-pages 10
```

### API + Dashboard

```bash
seo-api
# or: uvicorn app.api.app:app --reload --port 8000
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/health | Health |
| http://localhost:8000/docs | OpenAPI |
| http://localhost:8000/dashboard/ui?url=https://example.com/ | Operator dashboard |

Set `SEO_API_KEY` before exposing the service. Dashboard has an API key field for Bearer / `X-API-Key`.

### Docker

```bash
docker compose up --build
curl -sS http://127.0.0.1:8000/health
```

See [`docs/HOSTING.md`](docs/HOSTING.md). HTTPS deploy is optional for local/dev; park production OAuth Publish until you have a public domain.

---

## Common workflows

### Audit + save + compare

```bash
seo-audit https://example.com --save --max-pages 15
seo-audit https://example.com --compare --max-pages 15 -o audit.json
seo-history https://example.com
seo-compare https://example.com -o changes.md
```

### AI optimize (advice only)

Needs `OPENAI_API_KEY` (OpenAI-compatible via `LLM_BASE_URL` / `LLM_MODEL`):

```bash
seo-optimize https://example.com -o optimize.json --keywords "example domain,dns"
seo-audit https://example.com --optimize --keywords "example" --optimize-max-pages 3 -o out.json
```

### Reports + client scorecard share

```bash
seo-report --url https://example.com -o report.md --max-pages 5
seo-report --audit-id <id> -f pdf -o report.pdf
```

From the dashboard **Report / share** panel (after a saved audit):

1. Download PDF, or  
2. **Create client scorecard link** → public `/share/{token}` (no API key for viewers)  
3. PDF: `/share/{token}?format=pdf`

Audits, jobs, schedules, and share links default to SQLite (`SEO_STORAGE_PATH`, default `data/audits.db`). Use `SEO_DATABASE_URL` for Postgres (`pip install 'seo-agent[postgres]'`).

`POST /audit` with `background=true` enqueues a durable job; poll `GET /jobs/{job_id}`.

---

## Configuration

Defaults: [`config/default.yaml`](config/default.yaml)  
Env template: [`.env.example`](.env.example)

Never commit: `.env`, `secrets/`, `*.db`, local dumps (`out.json`, etc.).

---

## Status (high level)

- [x] Crawler, extractor, plugin analyzers, scoring, CLI  
- [x] AI optimize + keyword placement (advice only)  
- [x] Markdown / JSON / PDF reports + signal trust stubs  
- [x] Audit memory, compare, history  
- [x] FastAPI + operator dashboard  
- [x] GSC / GA4 Connect Google, PageSpeed, DataForSEO keywords + opt-in SERP/rank/backlinks  
- [x] Schedules, trends, alerts engine, public **client scorecard** share  
- [ ] Production HTTPS + OAuth Publish (owner — when you deploy)  
- [ ] Stripe / multi-tenant SaaS packaging (later)

---

## API snapshot

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health |
| POST | `/audit` | Run audit (`background=true` for async) |
| GET | `/jobs/{job_id}` | Poll job |
| POST | `/optimize` | AI page optimization advice |
| POST | `/keyword-plan` | On-page keyword placement |
| POST | `/report` | Generate report |
| GET | `/report/{audit_id}` | Saved report (`?format=pdf`) |
| POST | `/report/{audit_id}/share` | Create public scorecard link |
| GET | `/share/{token}` | Client scorecard (HTML) / PDF / markdown |
| GET | `/history?url=` | History |
| POST | `/compare` | Diff vs previous |
| GET | `/dashboard/ui` | Operator UI |

Full catalog and design notes: [`allinfo.md`](allinfo.md).

---

## Tests

```bash
pytest -q
```

---

## Embedding in a larger product

Run `seo-api` as a service; the parent product owns users/billing/UI and calls this API with `SEO_API_KEY`.  
The bundled dashboard is an operator console — production UX can be thinner and reuse the same endpoints. Details in `allinfo.md` §19.
