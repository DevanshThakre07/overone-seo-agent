"""OpenAI-style tool schemas for Hermes.

Descriptions are deliberately prescriptive: earlier sessions answered SEO
questions by delegating to generic subagents that grepped the local workspace
instead of fetching the site. Every tool here fetches the live URL itself, so
these must be preferred over delegation, shell tools, or file search.
"""

_NO_LOCAL_SEARCH = (
    "This tool fetches and renders the live URL over the network. "
    "NEVER delegate this work to a subagent, and NEVER search the local "
    "filesystem/workspace for the site's content — the website is not on this "
    "machine. If this tool reports a fetch failure, say so verbatim instead of "
    "substituting generic advice."
)

# A host agent once applied actoro.app's suggested copy to this project's own
# dashboard (hermes-agent/web/index.html) because it was the nearest index.html.
_RECOMMENDATIONS_ONLY = (
    "OUTPUT IS ADVICE, NOT A PATCH. The returned copy is for a human to apply on "
    "the external site. Do NOT create, edit, or patch ANY local file in response "
    "to this result, and never assume a local index.html/template/dashboard file "
    "is the target site's source. Honour the 'write_policy' field in the "
    "response. If the user wants local files edited, ask them which exact files "
    "correspond to the site before touching anything."
)

AUDIT_SITE = {
    "name": "audit_site",
    "description": (
        "Crawl a website and run a full technical/on-page SEO audit. "
        "Returns executive_summary (lead with this: score, severity, "
        "pagespeed_highlight, headline_issues — PageSpeed codes sorted first), "
        "top_issues, slim recommendations, rendering diagnostics, and optional "
        "comparison. Use generate_report for full markdown. " + _NO_LOCAL_SEARCH
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Seed URL to audit (e.g. https://example.com)",
            },
            "max_pages": {
                "type": "integer",
                "description": "Max pages to crawl (default from SEO-Agent config)",
            },
            "max_depth": {
                "type": "integer",
                "description": "Max crawl depth",
            },
            "save": {
                "type": "boolean",
                "description": "Persist audit to SQLite memory (default true)",
                "default": True,
            },
            "compare": {
                "type": "boolean",
                "description": "Compare with previous saved audit (default false)",
                "default": False,
            },
            "optimize": {
                "type": "boolean",
                "description": "Also run AI optimization on top pages (needs OPENAI_API_KEY)",
                "default": False,
            },
            "target_keywords": {
                "type": "string",
                "description": "Comma-separated target keywords for AI optimization",
            },
            "pagespeed": {
                "type": "boolean",
                "description": (
                    "Include PageSpeed Insights / Core Web Vitals on the seed URL. "
                    "Default: auto (runs when GOOGLE_PAGESPEED_API_KEY is set). "
                    "Set false to skip the ~15–60s PSI call."
                ),
            },
            "gsc_account_id": {
                "type": "string",
                "description": (
                    "Connected Google account_id (from /auth/google/start). "
                    "When set, merges Search Console opportunities "
                    "(page-2 rankings, low CTR) into recommendations. "
                    "Requires a verified GSC property matching the audit URL."
                ),
            },
            "auth_cookie": {
                "type": "string",
                "description": (
                    "Session Cookie header value for authenticated crawl. "
                    "Held in memory only for this call — never persisted. "
                    "IGNORED unless use_authenticated_crawl=true."
                ),
            },
            "auth_headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": (
                    "Extra HTTP headers for authenticated crawl "
                    "(e.g. Authorization). Memory-only; ignored unless "
                    "use_authenticated_crawl=true. Never logged or persisted."
                ),
            },
            "use_authenticated_crawl": {
                "type": "boolean",
                "description": (
                    "Conscious opt-in to use auth_cookie/auth_headers on GET/HEAD only. "
                    "Default false. Prefer check_login_wall first."
                ),
                "default": False,
            },
            "include_serp": {
                "type": "boolean",
                "description": (
                    "Opt-in paid DataForSEO SERP/rank enrichment for target_keywords "
                    "(max 3). Default false — never auto-runs."
                ),
                "default": False,
            },
            "include_backlinks": {
                "type": "boolean",
                "description": (
                    "Opt-in paid DataForSEO backlinks overview for the seed domain. "
                    "Default false — never auto-runs."
                ),
                "default": False,
            },
            "include_ga4": {
                "type": "boolean",
                "description": (
                    "Opt-in GA4 traffic snapshot on the audit. Requires "
                    "gsc_account_id (Connect Google). ga4_property_id optional "
                    "if a preferred property was saved (ga4_set_preference). "
                    "Default false — never auto-runs."
                ),
                "default": False,
            },
            "ga4_property_id": {
                "type": "string",
                "description": (
                    "GA4 property id from ga4_properties (e.g. 533500924). "
                    "Optional when a preferred property is saved for this account."
                ),
            },
        },
        "required": ["url"],
    },
}

CHECK_LOGIN_WALL = {
    "name": "check_login_wall",
    "description": (
        "Dry-run: fetch a URL WITHOUT credentials and report whether it looks like "
        "a login wall (login path, password field, 401/403). Use BEFORE asking the "
        "user for cookies. Never attaches auth. " + _NO_LOCAL_SEARCH
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to probe publicly (e.g. https://example.com/app)",
            },
        },
        "required": ["url"],
    },
}

CHECK_PAGESPEED = {
    "name": "check_pagespeed",
    "description": (
        "Run Google PageSpeed Insights for a LIVE URL: Lighthouse performance "
        "score, lab Core Web Vitals (LCP, CLS, INP), and field CrUX data when "
        "available. Use this for 'check vitals / PageSpeed / Core Web Vitals / "
        "how fast is this page' requests — do NOT run a full audit_site just for "
        "speed. Takes 15–60 seconds. Requires GOOGLE_PAGESPEED_API_KEY in "
        "SEO-Agent .env. " + _NO_LOCAL_SEARCH
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Page URL to measure (e.g. https://example.com)",
            },
            "strategy": {
                "type": "string",
                "enum": ["mobile", "desktop", "both"],
                "description": "Device strategy (default from PAGESPEED_STRATEGY / mobile)",
            },
        },
        "required": ["url"],
    },
}

RESEARCH_KEYWORDS = {
    "name": "research_keywords",
    "description": (
        "PRIMARY TOOL for any request about keyword research, search volume, "
        "CPC, competition, keyword difficulty, related keywords, or long-tail "
        "ideas. ALWAYS call this tool immediately — NEVER use search_files, "
        "grep, codebase_search, or local project search for keyword research "
        "(those only search this machine's files and cannot return Google volumes). "
        "Looks up REAL metrics via DataForSEO: search volume, CPC, competition, "
        "Labs keyword_difficulty (0–100), and related ideas for the first seed. "
        "NOT for on-page keyword placement (use keyword_plan for that). "
        "Requires KEYWORD_API_PROVIDER=dataforseo plus login/password. "
        "Never invent volumes if this tool fails."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "string",
                "description": "Comma-separated keywords (e.g. seo audit,core web vitals)",
            },
            "location_code": {
                "type": "integer",
                "description": "DataForSEO location code (default 2840 = United States)",
            },
            "language_code": {
                "type": "string",
                "description": "Language code (default en)",
            },
            "include_related": {
                "type": "boolean",
                "description": "Fetch related keywords for the first seed (default true)",
            },
            "include_difficulty": {
                "type": "boolean",
                "description": "Attach Labs keyword_difficulty scores (default true)",
            },
        },
        "required": ["keywords"],
    },
}

OPTIMIZE_PAGE = {
    "name": "optimize_page",
    "description": (
        "Generate SEO improvement suggestions for a single LIVE page: rewritten "
        "title, meta description, H1, headings, FAQs, schema, and internal links, "
        "plus keyword placement grounded in the page's actual copy. Returns "
        "'live_fetch' and 'page_evidence' proving which DOM was analyzed. "
        "Use this for any 'optimize/improve/keyword-integrate this URL' request. "
        + _NO_LOCAL_SEARCH
        + " "
        + _RECOMMENDATIONS_ONLY
        + " Requires OPENAI_API_KEY in SEO-Agent .env."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Page URL to optimize",
            },
            "target_keywords": {
                "type": "string",
                "description": "Comma-separated target keywords",
            },
            "auth_cookie": {
                "type": "string",
                "description": (
                    "Session Cookie for authenticated fetch. Memory-only; "
                    "ignored unless use_authenticated_crawl=true."
                ),
            },
            "auth_headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": (
                    "Extra HTTP headers (e.g. Authorization). Memory-only; "
                    "ignored unless use_authenticated_crawl=true."
                ),
            },
            "use_authenticated_crawl": {
                "type": "boolean",
                "description": (
                    "Opt in to use auth_cookie and/or auth_headers on GET only "
                    "(default false)."
                ),
                "default": False,
            },
        },
        "required": ["url"],
    },
}

KEYWORD_PLAN = {
    "name": "keyword_plan",
    "description": (
        "Given a URL and target keywords, fetch the live page and report exactly "
        "where each keyword is present or missing (title, meta description, H1, "
        "H2s, body copy), with concrete rewrite copy for each gap. No LLM/API key "
        "required. Use this whenever the user asks how to add/integrate keywords "
        "into a site. Note: it reports keyword PLACEMENT, not keyword research — "
        "search volume/difficulty require an external keyword API (see the "
        "'keyword_research' field in the response). "
        + _NO_LOCAL_SEARCH
        + " "
        + _RECOMMENDATIONS_ONLY
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Live page URL to analyze (e.g. https://example.com)",
            },
            "target_keywords": {
                "type": "string",
                "description": "Comma-separated keywords to place on the page",
            },
            "auth_cookie": {
                "type": "string",
                "description": (
                    "Session Cookie for authenticated fetch. Memory-only; "
                    "ignored unless use_authenticated_crawl=true."
                ),
            },
            "auth_headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": (
                    "Extra HTTP headers (e.g. Authorization). Memory-only; "
                    "ignored unless use_authenticated_crawl=true."
                ),
            },
            "use_authenticated_crawl": {
                "type": "boolean",
                "description": (
                    "Opt in to use auth_cookie and/or auth_headers on GET only "
                    "(default false)."
                ),
                "default": False,
            },
        },
        "required": ["url"],
    },
}

GENERATE_REPORT = {
    "name": "generate_report",
    "description": (
        "Generate a complete SEO report as markdown, JSON, or PDF. Provide either "
        "a url (runs a fresh audit first) or an existing audit_id. For markdown/JSON, "
        "returns the finished report in 'content' — write it verbatim to a file; "
        "do NOT hand-author your own report. For PDF, returns a file path "
        "(requires pip install 'seo-agent[pdf]'); do not dump base64 into chat. "
        + _NO_LOCAL_SEARCH
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to audit and report on",
            },
            "audit_id": {
                "type": "string",
                "description": "Existing saved audit id",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "json", "pdf"],
                "description": "Report format (default markdown; pdf needs seo-agent[pdf])",
                "default": "markdown",
            },
            "max_pages": {
                "type": "integer",
                "description": "Max pages when auditing from url",
            },
        },
        "required": [],
    },
}

COMPARE_AUDITS = {
    "name": "compare_audits",
    "description": (
        "Run a fresh SEO audit and compare it to the previous saved audit "
        "for the same URL. Returns score delta, new issues, and resolved issues. "
        + _NO_LOCAL_SEARCH
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Site URL to compare",
            },
            "max_pages": {
                "type": "integer",
                "description": "Max pages to crawl",
            },
        },
        "required": ["url"],
    },
}

CONFIRM_SITE_SOURCES = {
    "name": "confirm_site_sources",
    "description": (
        "Record which local files are genuinely the source of a site, after the "
        "USER has named them explicitly. This is the only way to lift the SEO "
        "write firewall, which otherwise blocks every write to markup/template "
        "files while an external site is being analyzed. "
        "NEVER call this with paths you inferred yourself from filenames such as "
        "index.html — ask the user which files correspond to the live site and "
        "pass exactly what they name. Paths inside an agent/tool codebase are "
        "always refused, even with user confirmation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The site URL these local files serve.",
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exact local file paths the USER identified as this site's "
                    "source. Must come from the user, not from your own search."
                ),
            },
        },
        "required": ["url", "paths"],
    },
}

LIST_SEO_HISTORY = {
    "name": "list_seo_history",
    "description": "List previously saved SEO audits for a URL from SEO-Agent memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Site URL",
            },
            "limit": {
                "type": "integer",
                "description": "Max audits to return (default 20)",
                "default": 20,
            },
        },
        "required": ["url"],
    },
}

LIST_SEO_TRENDS = {
    "name": "list_seo_trends",
    "description": (
        "Score and issue-severity trends over saved audits for a URL "
        "(retainer tracking). Requires prior audits with save=true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Site URL",
            },
            "limit": {
                "type": "integer",
                "description": "Max audit points (default 20)",
                "default": 20,
            },
        },
        "required": ["url"],
    },
}

LIST_RANK_HISTORY = {
    "name": "list_rank_history",
    "description": (
        "Keyword rank snapshots over time for a site/domain. "
        "Populated when audits run with include_serp + target_keywords, "
        "or when check_rank / GET /rank runs with save (default on)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Site URL (preferred)",
            },
            "target": {
                "type": "string",
                "description": "Domain if URL omitted",
            },
            "keyword": {
                "type": "string",
                "description": "Optional filter to one keyword",
            },
            "limit": {
                "type": "integer",
                "description": "Max snapshots (default 50)",
                "default": 50,
            },
        },
        "required": [],
    },
}

GSC_STATUS = {
    "name": "gsc_status",
    "description": (
        "Check whether a Google Search Console account_id is connected "
        "(OAuth done via browser /seo-api). Use before gsc_sites / "
        "gsc_performance. Does not start OAuth."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": (
                    "Customer account_id used at /auth/google/start "
                    "(e.g. bookasto)."
                ),
            },
        },
        "required": ["account_id"],
    },
}

GSC_SITES = {
    "name": "gsc_sites",
    "description": (
        "List verified Google Search Console properties for a connected "
        "account_id. Use the returned site_url values with gsc_performance "
        "or pass account_id into audit_site for enrichment. Requires prior "
        "Connect Google via /auth/google/start."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Connected Google account_id",
            },
        },
        "required": ["account_id"],
    },
}

GSC_PERFORMANCE = {
    "name": "gsc_performance",
    "description": (
        "Pull Google Search Console performance for a verified property: "
        "top queries/pages, clicks, CTR, position, and opportunities "
        "(page-2 rankings, low CTR). Prefer this over inventing ranking "
        "data. Requires connected account_id + exact site_url from gsc_sites "
        "(e.g. sc-domain:example.com)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Connected Google account_id",
            },
            "site_url": {
                "type": "string",
                "description": (
                    "Exact Search Console property URL "
                    "(e.g. sc-domain:example.com or https://example.com/)"
                ),
            },
            "days": {
                "type": "integer",
                "description": "Lookback window in days (default 28, max 90)",
                "default": 28,
            },
            "top_n": {
                "type": "integer",
                "description": "Max top queries/pages rows (default 20, max 50)",
                "default": 20,
            },
        },
        "required": ["account_id", "site_url"],
    },
}

GA4_STATUS = {
    "name": "ga4_status",
    "description": (
        "Check whether Connect Google account_id is ready for GA4 "
        "(has analytics.readonly). If false, user must re-open "
        "/auth/google/start to grant Analytics. Does not start OAuth."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Same account_id used at /auth/google/start",
            },
        },
        "required": ["account_id"],
    },
}

GA4_PROPERTIES = {
    "name": "ga4_properties",
    "description": (
        "List GA4 properties for a connected Google account_id (by display name). "
        "Also returns preferred_ga4_property_id if saved. "
        "Then call ga4_set_preference so audits can omit property_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Connected Google account_id",
            },
        },
        "required": ["account_id"],
    },
}

GA4_SET_PREFERENCE = {
    "name": "ga4_set_preference",
    "description": (
        "Save the user's preferred GA4 property for an account_id "
        "(pick by id from ga4_properties). After this, audit_site with "
        "include_ga4=true can omit ga4_property_id. Pass property_id empty/null to clear."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Connected Google account_id",
            },
            "property_id": {
                "type": "string",
                "description": "GA4 property id from ga4_properties (or empty to clear)",
            },
        },
        "required": ["account_id"],
    },
}

GA4_REPORT = {
    "name": "ga4_report",
    "description": (
        "Pull GA4 traffic snapshot: sessions, users, page views, and top pages. "
        "Requires connected account_id with Analytics scope. property_id optional "
        "if a preferred property was saved via ga4_set_preference."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Connected Google account_id",
            },
            "property_id": {
                "type": "string",
                "description": "GA4 property id (optional if preference saved)",
            },
            "days": {
                "type": "integer",
                "description": "Lookback window in days (default 28, max 90)",
                "default": 28,
            },
            "top_n": {
                "type": "integer",
                "description": "Max top pages rows (default 20, max 50)",
                "default": 20,
            },
        },
        "required": ["account_id"],
    },
}

CHECK_SERP = {
    "name": "check_serp",
    "description": (
        "PRIMARY TOOL for live Google organic SERP top results for a query. "
        "Uses paid DataForSEO — call only when the user asks for SERP / "
        "who ranks / competitors. Never invent rankings. "
        "Requires KEYWORD_API_PROVIDER=dataforseo credentials."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Search query (e.g. buy rare books online)",
            },
            "depth": {
                "type": "integer",
                "description": "Organic depth (default 10, max 100)",
                "default": 10,
            },
            "device": {
                "type": "string",
                "enum": ["desktop", "mobile"],
                "description": "Device (default desktop)",
            },
            "location_code": {
                "type": "integer",
                "description": "DataForSEO location code (default 2840 = US)",
            },
            "language_code": {
                "type": "string",
                "description": "Language code (default en)",
            },
        },
        "required": ["keyword"],
    },
}

CHECK_RANK = {
    "name": "check_rank",
    "description": (
        "Check where a domain ranks in Google organic results for a keyword "
        "(paid DataForSEO SERP). Use for 'what position is X for Y'. "
        "Never invent a position if this tool fails."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Keyword to rank-check",
            },
            "target": {
                "type": "string",
                "description": "Client domain or URL (e.g. bookasto.com)",
            },
            "depth": {
                "type": "integer",
                "description": "Organic depth to scan (default 20)",
                "default": 20,
            },
            "device": {
                "type": "string",
                "enum": ["desktop", "mobile"],
            },
        },
        "required": ["keyword", "target"],
    },
}

CHECK_BACKLINKS = {
    "name": "check_backlinks",
    "description": (
        "PRIMARY TOOL for backlink profile overview: total backlinks, "
        "referring domains, and top referring domains (paid DataForSEO). "
        "Call only when the user asks about backlinks / link profile. "
        "Never invent link counts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Domain or URL (e.g. bookasto.com)",
            },
            "referring_limit": {
                "type": "integer",
                "description": "Max top referring domains (default 10)",
                "default": 10,
            },
        },
        "required": ["target"],
    },
}
