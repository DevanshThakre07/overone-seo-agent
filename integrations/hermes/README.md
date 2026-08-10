# Hermes Integration (SEO-Agent side only)

This folder exposes the SEO engine to Hermes **without modifying** the `hermes-agent` repository.

```text
Telegram (later)
   ↓
Hermes Agent  (unchanged)
   ↓
~/.hermes/plugins/seo-agent  → symlink → SEO-Agent/integrations/hermes/seo_agent_plugin
   ↓
SEO-Agent tools/services
```

## One-time install

From the SEO-Agent repo:

```bash
chmod +x integrations/hermes/install_plugin.sh
./integrations/hermes/install_plugin.sh
```

If `hermes` is not on your PATH (`command not found: hermes`), enable the plugin manually by creating/editing **`~/.hermes/config.yaml`** (not the hermes-agent repo):

```yaml
plugins:
  enabled:
    - seo-agent
```

Or install Hermes first, then run `hermes plugins enable seo-agent`:

```bash
# Option A — official installer
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Option B — from your local clone
cd ../hermes-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
hermes plugins enable seo-agent
```

That only creates/updates:

- symlink: `~/.hermes/plugins/seo-agent` → this plugin folder
- user config: `~/.hermes/config.yaml` (`plugins.enabled`)

It never writes into `AI-AGENT-Projects/hermes-agent/`.

## Tools registered

| Tool | Purpose |
|---|---|
| `audit_site` | Crawl + SEO audit (optional save/compare/optimize/PageSpeed/GSC) |
| `check_pagespeed` | PageSpeed Insights / Core Web Vitals for a URL |
| `research_keywords` | DataForSEO search volume / CPC / competition |
| `optimize_page` | AI page suggestions |
| `keyword_plan` | Keyword placement gaps on a live page |
| `generate_report` | Markdown/JSON report |
| `compare_audits` | Diff vs previous audit |
| `confirm_site_sources` | Lift write firewall for user-named local source files |
| `list_seo_history` | List saved audits |
| `list_seo_trends` | Score / severity trends over saved audits |
| `gsc_status` | Whether a GSC `account_id` is connected |
| `gsc_sites` | List verified Search Console properties |
| `gsc_performance` | Queries / pages / opportunities for a property |
| `check_serp` | Live Google organic top results (paid DataForSEO) |
| `check_rank` | Domain position for a keyword (paid) |
| `check_backlinks` | Backlink summary + top referring domains (paid) |

Authenticated crawl: `audit_site`, `optimize_page`, and `keyword_plan` accept `auth_cookie`, `auth_headers`, and `use_authenticated_crawl` (GET/HEAD only, memory-only). Connect Google via browser/`seo-api` OAuth — Hermes does not start the consent flow.

Competitive SEO is **opt-in only** (never auto on audit): use the tools above, or pass `include_serp` / `include_backlinks` on `audit_site` when the user explicitly asks.

## Requirements

- SEO-Agent installed in its venv (`pip install -e ".[dev]"`)
- SEO-Agent `.env` with `OPENAI_API_KEY` for optimize
- `GOOGLE_PAGESPEED_API_KEY` for `check_pagespeed` / audit CWV enrichment
- `KEYWORD_API_PROVIDER=dataforseo` + login/password for `research_keywords`
- Hermes can import the SEO-Agent `app` package (plugin adds SEO-Agent root to `sys.path`)

## Optional: HTTP instead of in-process

If you prefer process isolation, run `seo-api` and call HTTP from a future MCP adapter. The native plugin above is the default Hermes path.

## Uninstall

```bash
rm ~/.hermes/plugins/seo-agent
# then remove seo-agent from plugins.enabled in ~/.hermes/config.yaml
```
