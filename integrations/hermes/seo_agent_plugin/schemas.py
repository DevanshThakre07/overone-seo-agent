"""OpenAI-style tool schemas for Hermes."""

AUDIT_SITE = {
    "name": "audit_site",
    "description": (
        "Crawl a website and run a full technical/on-page SEO audit. "
        "Returns score, issues, page extractions, and optional comparison "
        "against the previous saved audit."
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
        },
        "required": ["url"],
    },
}

OPTIMIZE_PAGE = {
    "name": "optimize_page",
    "description": (
        "Generate AI SEO improvement suggestions for a single page: "
        "title, meta description, H1, headings, keywords, FAQs, schema, "
        "and internal links. Requires OPENAI_API_KEY in SEO-Agent .env."
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

GENERATE_REPORT = {
    "name": "generate_report",
    "description": (
        "Generate a downloadable SEO report in markdown or JSON. "
        "Provide either a url (runs audit first) or an existing audit_id."
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
        "for the same URL. Returns score delta, new issues, and resolved issues."
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
