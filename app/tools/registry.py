from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._tools[name] = func

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def call(self, name: str, **kwargs: Any) -> Any:
        return self.get(name)(**kwargs)


def get_default_registry() -> ToolRegistry:
    from app.tools import (
        audit_tool,
        compare_tool,
        crawler_tool,
        backlinks_tool,
        ga4_tool,
        gsc_tool,
        history_tool,
        keyword_plan_tool,
        keyword_research_tool,
        login_wall_tool,
        optimize_tool,
        pagespeed_tool,
        rank_history_tool,
        report_tool,
        serp_tool,
        trends_tool,
    )

    registry = ToolRegistry()
    registry.register("crawl_site", crawler_tool.crawl_site)
    registry.register("audit_site", audit_tool.audit_site)
    registry.register("check_login_wall", login_wall_tool.check_login_wall)
    registry.register("generate_report", report_tool.generate_report)
    registry.register("optimize_page", optimize_tool.optimize_page)
    registry.register("keyword_plan", keyword_plan_tool.keyword_plan)
    registry.register("compare_audits", compare_tool.compare_audits)
    registry.register("list_history", history_tool.list_history)
    registry.register("generate_change_report", compare_tool.generate_change_report)
    registry.register("check_pagespeed", pagespeed_tool.check_pagespeed)
    registry.register("pagespeed_status", pagespeed_tool.pagespeed_status)
    registry.register(
        "research_keywords", keyword_research_tool.research_keywords_tool
    )
    registry.register(
        "keyword_research_status", keyword_research_tool.keyword_research_status
    )
    registry.register("gsc_status", gsc_tool.gsc_status)
    registry.register("gsc_list_sites", gsc_tool.gsc_list_sites)
    registry.register("gsc_performance", gsc_tool.gsc_performance)
    registry.register("ga4_status", ga4_tool.ga4_status)
    registry.register("ga4_list_properties", ga4_tool.ga4_list_properties)
    registry.register("ga4_set_preference", ga4_tool.ga4_set_preference)
    registry.register("ga4_get_preference", ga4_tool.ga4_get_preference)
    registry.register("ga4_report", ga4_tool.ga4_report)
    registry.register("check_serp", serp_tool.check_serp)
    registry.register("check_rank", serp_tool.check_rank)
    registry.register("list_rank_history", rank_history_tool.list_rank_history)
    registry.register("check_backlinks", backlinks_tool.check_backlinks)
    registry.register("list_seo_trends", trends_tool.list_seo_trends)
    return registry
