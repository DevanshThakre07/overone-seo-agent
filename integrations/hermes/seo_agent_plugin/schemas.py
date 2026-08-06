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
        "Returns score, issues, per-page extractions, prescriptive "
        "recommendations, rendering diagnostics, and optional comparison "
        "against the previous saved audit. " + _NO_LOCAL_SEARCH
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
        "Look up REAL keyword metrics via DataForSEO: search volume, CPC, "
        "competition, Labs keyword_difficulty (0–100), and related/long-tail "
        "ideas for the first seed. Use for 'keyword research / search volume / "
        "difficulty / related keywords' requests. NOT page placement "
        "(use keyword_plan for that). Requires KEYWORD_API_PROVIDER=dataforseo "
        "plus login/password. Never invent volumes if this tool fails."
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
        },
        "required": ["url"],
    },
}

GENERATE_REPORT = {
    "name": "generate_report",
    "description": (
        "Generate a complete SEO report as clean markdown or JSON. Provide either "
        "a url (runs a fresh audit first) or an existing audit_id. Returns the "
        "finished report in the 'content' field — write that content verbatim to "
        "a file if the user wants a file; do NOT hand-author your own report, and "
        "do NOT write it through a patch/diff tool (that adds '+' line prefixes). "
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
                "enum": ["markdown", "json"],
                "description": "Report format (default markdown)",
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
