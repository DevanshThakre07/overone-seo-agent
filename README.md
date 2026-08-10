# AI SEO Agent

Standalone, modular SEO engine: crawl → extract → plugin analyzers → structured JSON audit.

Designed to later plug into Hermes as tools and a multi-agent Growth Copilot — without coupling the core to Hermes or Telegram.

## Architecture

```text
CLI / Future FastAPI / Future Hermes adapter
        ↓
   tools/  (audit_site, crawl_site, …)
        ↓
   services/  (SeoService, CrawlerService, …)
        ↓
 crawler / extractor / analyzers / repositories
```

Each SEO check is an independent plugin under `app/analyzers/`, executed by `AnalyzerRegistry`.

## Quick start

Requires **Python 3.11+** (3.12 recommended).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

seo-audit https://example.com -o out.json --max-pages 10
# or
python -m app.main https://example.com -o out.json --max-pages 10
```

### Phase 2 — AI optimize

Set `OPENAI_API_KEY` (OpenAI-compatible APIs also work via `LLM_BASE_URL` / `LLM_MODEL`):

```bash
cp .env.example .env   # then add your key

# Single page suggestions
seo-optimize https://example.com -o optimize.json --keywords "example domain,dns"

# Audit + optimize top pages
seo-audit https://example.com --optimize --keywords "example" --optimize-max-pages 3 -o out.json
```

Suggestions include improved title/meta/H1, headings, keywords, FAQs, schema, and internal links — grounded in extracted page facts only.

### Phase 3 — Reports

```bash
# Markdown report (default)
seo-report --url https://example.com -o report.md --max-pages 5

# Structured JSON report sections
seo-report --url https://example.com -f json -o report.json

# PDF (requires: pip install 'seo-agent[pdf]')
seo-report --audit-id <id> -f pdf -o report.pdf

# From a saved audit id (requires --save on audit/report)
seo-report --audit-id <id> -f markdown -o report.md
```

Each report includes: Summary, Critical Issues, Warnings, Suggestions, Overall SEO Score.  
PDF download: `GET /report/{audit_id}?format=pdf` or public `GET /share/{token}?format=pdf`.

### Phase 4 — Memory & compare

```bash
# Save baseline
seo-audit https://example.com --save --max-pages 5

# Later: compare against previous (auto-saves current)
seo-audit https://example.com --compare --max-pages 5 -o audit.json
seo-compare https://example.com -o changes.md --max-pages 5
seo-history https://example.com
```

Audits, background jobs, schedules, and share links default to SQLite (`SEO_STORAGE_PATH`, default `data/audits.db`). Set `SEO_DATABASE_URL` or `DATABASE_URL` to use Postgres for all of them (`pip install 'seo-agent[postgres]'`). `POST /audit` with `background=true` (and due schedules) enqueue durable jobs; poll `GET /jobs/{job_id}` (`pending|running|completed|failed`).

### Phase 5 — FastAPI

```bash
seo-api
# or: uvicorn app.api.app:app --reload --port 8000
```

OpenAPI docs: http://localhost:8000/docs

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/audit` | Run audit (`background=true` for async job) |
| GET | `/jobs/{job_id}` | Poll background job |
| POST | `/optimize` | AI page optimization |
| POST | `/report` | Generate report from url or audit_id |
| GET | `/report/{audit_id}` | Fetch saved audit report |
| GET | `/history?url=` | List saved audits |
| POST | `/compare` | Compare with previous audit |

## Configuration

Defaults: [`config/default.yaml`](config/default.yaml)  
Env overrides: [`.env.example`](.env.example)

## Status

- [x] Phase 1: crawler, extractor, plugin analyzers, services, tools, CLI
- [x] Phase 2: AI optimizer (`OptimizerService`, `seo-optimize`, `--optimize`)
- [x] Phase 3: JSON/Markdown/PDF reports (`seo-report`; PDF via `seo-agent[pdf]`)
- [x] Phase 4: SQLite memory, compare/history, change reports
- [x] Phase 5: FastAPI (`seo-api`, OpenAPI at `/docs`)
- [x] Hermes plugin adapter (in SEO-Agent only; symlink to `~/.hermes/plugins/`)
- [ ] Telegram (via Hermes later)

### Hermes plugin (does not modify hermes-agent)

```bash
./integrations/hermes/install_plugin.sh
hermes plugins enable seo-agent
```

See [integrations/hermes/README.md](integrations/hermes/README.md).

## Tests

```bash
pytest -q
```

## Hermes-ready tools

Registered in `app/tools/registry.py`:

- `audit_site`
- `crawl_site`
- `generate_report`
- `optimize_page` (stub)
- `compare_audits`
