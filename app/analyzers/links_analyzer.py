from __future__ import annotations

from collections import defaultdict

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity
from app.utils.url import normalize_url

_MAX_GRAPH_SAMPLES = 8
_FEW_INTERNAL_LINKS = 2


class LinksAnalyzer:
    name = "links"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        broken_pages = 0
        broken_external = 0
        redirect_chains = 0
        internal_unique = 0
        external_unique = 0
        internal_occurrences = 0
        external_occurrences = 0
        pages_without_internal_links = 0

        for page in context.pages:
            internal_unique += len(page.internal_links)
            external_unique += len(page.external_links)
            internal_occurrences += page.internal_link_occurrences or len(page.internal_links)
            external_occurrences += page.external_link_occurrences or len(page.external_links)

            if page.is_broken:
                broken_pages += 1
                issues.append(
                    Issue(
                        code="broken_page",
                        severity=Severity.CRITICAL,
                        message=page.error or "Broken page (HTTP error during crawl)",
                        url=page.final_url,
                        details={
                            "status_code": page.status_code,
                            "requested_url": page.url,
                        },
                    )
                )
            elif not page.internal_links and not page.is_broken:
                pages_without_internal_links += 1
                likely_shell = bool((page.seo_signals or {}).get("likely_js_shell"))
                if likely_shell or page.word_count > 0:
                    issues.append(
                        Issue(
                            code="no_internal_links",
                            severity=Severity.INFO,
                            message="Page has no crawlable internal links",
                            url=page.final_url,
                            details={
                                "word_count": page.word_count,
                                "likely_js_shell": likely_shell,
                                "js_rendered": page.js_rendered,
                            },
                        )
                    )

            if len(page.redirect_chain) > 1:
                redirect_chains += 1
                issues.append(
                    Issue(
                        code="redirect_chain",
                        # Informational: locale/trailing-slash/https redirects are
                        # normal. Reported for visibility, not scored as a defect.
                        severity=Severity.INFO,
                        message=f"Redirect chain with {len(page.redirect_chain)} hops",
                        url=page.url,
                        details={"chain": page.redirect_chain},
                    )
                )

        # External probes stored as crawl_results with depth == -1.
        # Cap + INFO: outbound 404s are noisy and often not under the client's
        # control; keep a sample for visibility without flooding the score.
        _MAX_BROKEN_EXTERNAL_ISSUES = 5
        for result in context.crawl_results:
            if result.depth == -1 and result.is_broken:
                broken_external += 1
                if broken_external <= _MAX_BROKEN_EXTERNAL_ISSUES:
                    issues.append(
                        Issue(
                            code="broken_external_link",
                            severity=Severity.INFO,
                            message=result.error or "Broken external link",
                            url=result.url,
                            details={"status_code": result.status_code},
                        )
                    )
        if broken_external > _MAX_BROKEN_EXTERNAL_ISSUES:
            issues.append(
                Issue(
                    code="broken_external_link_summary",
                    severity=Severity.INFO,
                    message=(
                        f"{broken_external} broken external links detected "
                        f"(showing {_MAX_BROKEN_EXTERNAL_ISSUES} samples). "
                        "Review outbound links when they affect UX or trust."
                    ),
                    url=context.seed_url,
                    details={"broken_external_links": broken_external},
                )
            )

        graph_metrics = self._analyze_internal_graph(context, issues)

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "broken": broken_pages + broken_external,
                "broken_pages": broken_pages,
                "broken_external_links": broken_external,
                "redirect_chains": redirect_chains,
                "internal_links_unique": internal_unique,
                "external_links_unique": external_unique,
                "internal_link_occurrences": internal_occurrences,
                "external_link_occurrences": external_occurrences,
                "pages_without_internal_links": pages_without_internal_links,
                **graph_metrics,
            },
        )

    def _analyze_internal_graph(
        self, context: AnalysisContext, issues: list[Issue]
    ) -> dict:
        """Directed graph over live crawled pages (crawl-scoped, not whole site)."""
        live = [p for p in context.pages if not p.is_broken]
        if len(live) < 2:
            return {
                "graph_nodes": len(live),
                "graph_edges": 0,
                "orphan_pages": 0,
                "dead_end_pages": 0,
                "pages_few_internal_links": 0,
                "avg_out_degree": 0.0,
                "avg_in_degree": 0.0,
                "max_in_degree": 0,
                "max_out_degree": 0,
                "hub_url": None,
                "hub_out_share": 0.0,
                "graph_note": (
                    "Internal link graph needs 2+ live crawled pages "
                    "(current crawl is too small for orphan/hub signals)."
                ),
            }

        seed_norm = normalize_url(context.seed_url)
        nodes: set[str] = set()
        page_by_node: dict[str, object] = {}
        for page in live:
            node = normalize_url(page.final_url or page.url)
            nodes.add(node)
            page_by_node[node] = page
            req = normalize_url(page.url)
            if req and req not in page_by_node:
                page_by_node[req] = page

        out_edges: dict[str, set[str]] = defaultdict(set)
        for page in live:
            src = normalize_url(page.final_url or page.url)
            for target in page.internal_links or []:
                dst = normalize_url(target)
                if dst in nodes and dst != src:
                    out_edges[src].add(dst)

        in_degree: dict[str, int] = {n: 0 for n in nodes}
        edge_count = 0
        for src, targets in out_edges.items():
            edge_count += len(targets)
            for dst in targets:
                in_degree[dst] = in_degree.get(dst, 0) + 1

        out_degree = {n: len(out_edges.get(n, ())) for n in nodes}
        orphans = [n for n in nodes if n != seed_norm and in_degree.get(n, 0) == 0]
        dead_ends = [n for n in nodes if out_degree.get(n, 0) == 0]
        few_out = [
            n for n in nodes if 0 < out_degree.get(n, 0) < _FEW_INTERNAL_LINKS
        ]

        for url in orphans[:_MAX_GRAPH_SAMPLES]:
            issues.append(
                Issue(
                    code="orphan_page",
                    severity=Severity.WARNING,
                    message=(
                        "Page has no inbound links from other crawled pages "
                        "(orphan in this crawl graph — may still be linked "
                        "from uncrawled URLs)."
                    ),
                    url=url,
                    details={"in_degree": 0, "crawl_scoped": True},
                )
            )
        if len(orphans) > _MAX_GRAPH_SAMPLES:
            issues.append(
                Issue(
                    code="orphan_pages_summary",
                    severity=Severity.INFO,
                    message=(
                        f"{len(orphans)} orphan pages in the crawl graph "
                        f"(showing {_MAX_GRAPH_SAMPLES} samples). "
                        "Add internal links from hubs/nav where appropriate."
                    ),
                    url=context.seed_url,
                    details={"orphan_pages": len(orphans)},
                )
            )

        already_no_internal = {
            normalize_url(i.url)
            for i in issues
            if i.code == "no_internal_links" and i.url
        }
        dead_end_samples = 0
        for url in dead_ends:
            if url in already_no_internal:
                continue
            page = page_by_node.get(url)
            raw_internal = len(getattr(page, "internal_links", None) or [])
            if raw_internal == 0:
                continue
            if dead_end_samples >= _MAX_GRAPH_SAMPLES:
                break
            dead_end_samples += 1
            issues.append(
                Issue(
                    code="dead_end_page",
                    severity=Severity.INFO,
                    message=(
                        "Page has internal links, but none point to other "
                        "pages in this crawl (dead-end within the crawl graph)."
                    ),
                    url=url,
                    details={
                        "out_degree_crawled": 0,
                        "raw_internal_links": raw_internal,
                        "crawl_scoped": True,
                    },
                )
            )

        for url in few_out[:_MAX_GRAPH_SAMPLES]:
            issues.append(
                Issue(
                    code="few_internal_links",
                    severity=Severity.INFO,
                    message=(
                        f"Page links to fewer than {_FEW_INTERNAL_LINKS} other "
                        "crawled pages — thin internal linking within this crawl."
                    ),
                    url=url,
                    details={
                        "out_degree_crawled": out_degree.get(url, 0),
                        "threshold": _FEW_INTERNAL_LINKS,
                        "crawl_scoped": True,
                    },
                )
            )

        hub_url = None
        hub_out = 0
        hub_share = 0.0
        if edge_count > 0:
            hub_url = max(nodes, key=lambda n: out_degree.get(n, 0))
            hub_out = out_degree.get(hub_url, 0)
            hub_share = hub_out / edge_count if edge_count else 0.0
            if hub_share >= 0.4 and hub_out >= 3 and len(nodes) >= 3:
                issues.append(
                    Issue(
                        code="hub_concentration",
                        severity=Severity.INFO,
                        message=(
                            f"Internal link hub concentration: one page emits "
                            f"{hub_share:.0%} of crawl-graph edges "
                            f"({hub_out}/{edge_count}). Consider distributing "
                            "links across templates/nav."
                        ),
                        url=hub_url,
                        details={
                            "hub_out_degree": hub_out,
                            "graph_edges": edge_count,
                            "hub_out_share": round(hub_share, 3),
                            "crawl_scoped": True,
                        },
                    )
                )

        n = len(nodes)
        avg_out = (sum(out_degree.values()) / n) if n else 0.0
        avg_in = (sum(in_degree.values()) / n) if n else 0.0
        return {
            "graph_nodes": n,
            "graph_edges": edge_count,
            "orphan_pages": len(orphans),
            "dead_end_pages": len(dead_ends),
            "pages_few_internal_links": len(few_out),
            "avg_out_degree": round(avg_out, 2),
            "avg_in_degree": round(avg_in, 2),
            "max_in_degree": max(in_degree.values()) if in_degree else 0,
            "max_out_degree": max(out_degree.values()) if out_degree else 0,
            "hub_url": hub_url,
            "hub_out_share": round(hub_share, 3),
            "graph_note": (
                "Graph is limited to crawled pages — orphans mean "
                "not linked from other URLs in this crawl."
            ),
        }
