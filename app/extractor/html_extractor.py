"""HTML → PageExtraction (no network I/O)."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.models.crawl import CrawlResult
from app.models.page import ImageInfo, PageExtraction
from app.utils.url import is_same_host, resolve_url

_SKIP_HREF_PREFIXES = ("javascript:", "mailto:", "tel:", "sms:", "data:", "blob:")
_IMG_SRC_ATTRS = (
    "src",
    "data-src",
    "data-lazy-src",
    "data-original",
    "data-lazy",
    "data-url",
    "data-image",
)


class HtmlExtractor:
    def extract(self, crawl_result: CrawlResult, seed_url: str) -> PageExtraction:
        if crawl_result.is_broken or not crawl_result.html:
            return PageExtraction(
                url=crawl_result.url,
                final_url=crawl_result.final_url,
                status_code=crawl_result.status_code,
                content_length=crawl_result.content_length,
                redirect_chain=[h.url for h in crawl_result.redirect_chain],
                is_broken=True,
                error=crawl_result.error or f"HTTP {crawl_result.status_code}",
                js_rendered=crawl_result.js_rendered,
            )

        soup = self._soup(crawl_result.html)
        warnings: list[str] = []

        html_tag = soup.find("html")
        lang = None
        if isinstance(html_tag, Tag):
            lang = (html_tag.get("lang") or html_tag.get("xml:lang") or "").strip() or None

        has_viewport = bool(
            soup.find(
                "meta",
                attrs={"name": lambda v: isinstance(v, str) and v.lower() == "viewport"},
            )
        )

        og_title = self._meta_content(soup, property_name="og:title")
        og_description = self._meta_content(soup, property_name="og:description")
        twitter_title = self._meta_content(soup, name="twitter:title")
        twitter_description = self._meta_content(soup, name="twitter:description")

        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        title: str | None = None
        title_source: str | None = None
        if title_text:
            title = title_text
            title_source = "title"
        elif og_title:
            title = og_title
            title_source = "og:title"
            warnings.append("title_fallback_og")
        elif twitter_title:
            title = twitter_title
            title_source = "twitter:title"
            warnings.append("title_fallback_twitter")

        meta_desc = self._meta_content(soup, name="description")
        meta_source: str | None = "description" if meta_desc else None
        if not meta_desc and og_description:
            meta_desc = og_description
            meta_source = "og:description"
            warnings.append("meta_description_fallback_og")
        elif not meta_desc and twitter_description:
            meta_desc = twitter_description
            meta_source = "twitter:description"
            warnings.append("meta_description_fallback_twitter")

        robots_meta = self._meta_content(soup, name="robots")
        if not robots_meta:
            robots_meta = self._meta_content(soup, name="googlebot")

        canonical = self._extract_canonical(soup, crawl_result.final_url)

        h1 = self._heading_texts(soup, "h1")
        h2 = self._heading_texts(soup, "h2")
        h3 = self._heading_texts(soup, "h3")
        h4 = self._heading_texts(soup, "h4")
        h5 = self._heading_texts(soup, "h5")
        h6 = self._heading_texts(soup, "h6")

        images = self._extract_images(soup, crawl_result.final_url)
        (
            internal,
            external,
            internal_occurrences,
            external_occurrences,
        ) = self._extract_links(soup, crawl_result.final_url, seed_url)

        schema_types, has_json_ld, schema_script_count = self._extract_schema(soup)
        if schema_script_count and not has_json_ld:
            warnings.append("json_ld_present_but_unparsed")

        visible_text = self._visible_text(soup)
        word_count = len(re.findall(r"\b\w+\b", visible_text))
        text_length = len(visible_text)

        html_bytes = len(crawl_result.html.encode("utf-8", errors="ignore"))
        content_length = crawl_result.content_length or html_bytes
        # Prefer real HTML size when header under-reports a rendered body.
        if html_bytes > content_length:
            content_length = html_bytes

        seo_signals = {
            "title_length": len(title) if title else 0,
            "meta_description_length": len(meta_desc) if meta_desc else 0,
            "h1_count": len(h1),
            "h2_count": len(h2),
            "h3_count": len(h3),
            "h4_count": len(h4),
            "h5_count": len(h5),
            "h6_count": len(h6),
            "heading_count": len(h1) + len(h2) + len(h3) + len(h4) + len(h5) + len(h6),
            "image_count": len(images),
            "images_missing_alt": sum(
                1
                for img in images
                if not img.alt_present and not img.decorative and not img.is_source
            ),
            "images_decorative": sum(1 for img in images if img.decorative),
            "unique_internal_links": len(internal),
            "unique_external_links": len(external),
            "internal_link_occurrences": internal_occurrences,
            "external_link_occurrences": external_occurrences,
            "word_count": word_count,
            "text_length": text_length,
            "schema_type_count": len(schema_types),
            "has_canonical": bool(canonical),
            "has_robots_meta": bool(robots_meta),
            "has_viewport": has_viewport,
            "has_lang": bool(lang),
            "js_rendered": crawl_result.js_rendered,
            "likely_js_shell": self._looks_like_js_shell(
                soup, h1=h1, images=images, internal=internal, word_count=word_count
            ),
        }
        if seo_signals["likely_js_shell"]:
            warnings.append("likely_js_shell")

        return PageExtraction(
            url=crawl_result.url,
            final_url=crawl_result.final_url,
            status_code=crawl_result.status_code,
            title=title,
            meta_description=meta_desc,
            h1=h1,
            h2=h2,
            h3=h3,
            h4=h4,
            h5=h5,
            h6=h6,
            images=images,
            canonical=canonical,
            robots_meta=robots_meta,
            internal_links=internal,
            external_links=external,
            content_length=content_length,
            redirect_chain=[h.url for h in crawl_result.redirect_chain],
            is_broken=False,
            has_json_ld=has_json_ld,
            schema_types=schema_types,
            title_source=title_source,
            meta_description_source=meta_source,
            og_title=og_title,
            og_description=og_description,
            twitter_title=twitter_title,
            twitter_description=twitter_description,
            lang=lang,
            has_viewport=has_viewport,
            word_count=word_count,
            text_length=text_length,
            internal_link_occurrences=internal_occurrences,
            external_link_occurrences=external_occurrences,
            image_count=len(images),
            js_rendered=crawl_result.js_rendered,
            text_sample=visible_text[:5000],
            extraction_warnings=warnings,
            seo_signals={
                **seo_signals,
                "render_diagnostics": crawl_result.render_diagnostics or {},
            },
        )

    def extract_many(
        self, crawl_results: list[CrawlResult], seed_url: str
    ) -> list[PageExtraction]:
        # Skip synthetic external-only probes (depth == -1) from page list;
        # they are still available via crawl results for link analysis.
        pages = [r for r in crawl_results if r.depth >= 0]
        return [self.extract(r, seed_url) for r in pages]

    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        """Prefer lxml; fall back to stdlib html.parser if lxml is unavailable."""
        try:
            return BeautifulSoup(html, "lxml")
        except Exception:
            return BeautifulSoup(html, "html.parser")

    def _meta_content(
        self,
        soup: BeautifulSoup,
        *,
        name: str | None = None,
        property_name: str | None = None,
    ) -> str | None:
        if name:
            tag = soup.find(
                "meta",
                attrs={"name": lambda v: isinstance(v, str) and v.lower() == name.lower()},
            )
            if tag and tag.get("content"):
                value = str(tag["content"]).strip()
                return value or None
        if property_name:
            tag = soup.find(
                "meta",
                attrs={
                    "property": lambda v: isinstance(v, str)
                    and v.lower() == property_name.lower()
                },
            )
            if tag and tag.get("content"):
                value = str(tag["content"]).strip()
                return value or None
        return None

    def _extract_canonical(self, soup: BeautifulSoup, base_url: str) -> str | None:
        for tag in soup.find_all("link", href=True):
            rel = tag.get("rel")
            tokens: list[str] = []
            if isinstance(rel, list):
                tokens = [str(x).lower() for x in rel]
            elif isinstance(rel, str):
                tokens = [part.strip().lower() for part in rel.split()]
            if "canonical" in tokens:
                href = str(tag["href"]).strip()
                if href:
                    return resolve_url(base_url, href) or href
        return None

    def _heading_texts(self, soup: BeautifulSoup, tag_name: str) -> list[str]:
        texts: list[str] = []
        for heading in soup.find_all(tag_name):
            text = heading.get_text(" ", strip=True)
            if text:
                texts.append(text)
        return texts

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[ImageInfo]:
        images: list[ImageInfo] = []
        seen: set[str] = set()

        for img in soup.find_all("img"):
            src = self._image_src(img)
            if not src:
                continue
            resolved = resolve_url(base_url, src) or src
            if resolved in seen:
                continue
            seen.add(resolved)
            alt = img.get("alt")
            images.append(
                ImageInfo(
                    src=resolved,
                    alt=alt if alt is not None else None,
                    alt_present=alt is not None,
                    decorative=self._is_decorative(img, alt),
                )
            )

        # <picture><source srcset=...> without a usable <img src>
        for source in soup.find_all("source"):
            parent = source.parent
            if not isinstance(parent, Tag) or parent.name != "picture":
                continue
            src = self._srcset_first(source.get("srcset"))
            if not src:
                continue
            resolved = resolve_url(base_url, src) or src
            if resolved in seen:
                continue
            seen.add(resolved)
            images.append(ImageInfo(src=resolved, alt=None, is_source=True))

        return images

    @staticmethod
    def _is_decorative(img: Tag, alt: str | None) -> bool:
        """Images that correctly have no accessible name.

        Per WAI-ARIA, alt="", role="presentation"/"none" and aria-hidden="true"
        all mark an image as decorative. 1x1 images are tracking pixels.
        """
        if alt is not None and alt == "":
            return True
        if str(img.get("role", "")).strip().lower() in {"presentation", "none"}:
            return True
        if str(img.get("aria-hidden", "")).strip().lower() == "true":
            return True
        for attr in ("width", "height"):
            raw = str(img.get(attr, "")).strip().rstrip("px")
            if raw.isdigit() and int(raw) <= 1:
                return True
        return False

    def _image_src(self, img: Tag) -> str:
        for attr in _IMG_SRC_ATTRS:
            value = img.get(attr)
            if isinstance(value, str) and value.strip():
                return value.strip()
        srcset = img.get("srcset")
        if isinstance(srcset, str) and srcset.strip():
            first = self._srcset_first(srcset)
            if first:
                return first
        return ""

    def _srcset_first(self, srcset: Any) -> str | None:
        if not isinstance(srcset, str) or not srcset.strip():
            return None
        # "image.webp 1x, image@2x.webp 2x" → first URL token
        first = srcset.split(",")[0].strip().split()
        return first[0] if first else None

    def _extract_links(
        self, soup: BeautifulSoup, base_url: str, seed_url: str
    ) -> tuple[list[str], list[str], int, int]:
        internal: list[str] = []
        external: list[str] = []
        internal_seen: set[str] = set()
        external_seen: set[str] = set()
        internal_occurrences = 0
        external_occurrences = 0

        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            lowered = href.lower()
            if lowered.startswith(_SKIP_HREF_PREFIXES):
                continue
            resolved = resolve_url(base_url, href)
            if not resolved:
                continue
            if is_same_host(seed_url, resolved):
                internal_occurrences += 1
                if resolved not in internal_seen:
                    internal_seen.add(resolved)
                    internal.append(resolved)
            else:
                external_occurrences += 1
                if resolved not in external_seen:
                    external_seen.add(resolved)
                    external.append(resolved)

        return internal, external, internal_occurrences, external_occurrences

    def _extract_schema(self, soup: BeautifulSoup) -> tuple[list[str], bool, int]:
        types: list[str] = []
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        parsed_ok = False
        for script in scripts:
            raw = script.string or script.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Common: trailing commas / HTML comments inside JSON-LD
                cleaned = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
                cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
            parsed_ok = True
            self._collect_schema_types(data, types)

        # Preserve order, drop duplicates
        deduped: list[str] = []
        seen: set[str] = set()
        for item in types:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped, parsed_ok and bool(deduped or scripts), len(scripts)

    def _collect_schema_types(self, node: Any, types: list[str]) -> None:
        if isinstance(node, list):
            for item in node:
                self._collect_schema_types(item, types)
            return
        if not isinstance(node, dict):
            return

        t = node.get("@type")
        if isinstance(t, list):
            types.extend(str(x) for x in t if x)
        elif t:
            types.append(str(t))

        graph = node.get("@graph")
        if graph is not None:
            self._collect_schema_types(graph, types)

        for key, value in node.items():
            if key in {"@type", "@context", "@graph"}:
                continue
            if isinstance(value, (dict, list)):
                self._collect_schema_types(value, types)

    def _visible_text(self, soup: BeautifulSoup) -> str:
        # Work on a clone so later soup queries (e.g. JS-shell heuristics) stay intact.
        clone = self._soup(str(soup))
        for tag in clone(["script", "style", "noscript", "svg", "template"]):
            tag.decompose()
        return clone.get_text(" ", strip=True)

    def _looks_like_js_shell(
        self,
        soup: BeautifulSoup,
        *,
        h1: list[str],
        images: list[ImageInfo],
        internal: list[str],
        word_count: int,
    ) -> bool:
        rootish = soup.find(
            id=lambda v: isinstance(v, str) and v.lower() in {"root", "app", "__next", "___gatsby"}
        )
        semantic = len(h1) + len(images) + len(internal)
        if rootish is not None and semantic == 0 and word_count < 80:
            return True
        if semantic == 0 and word_count < 40:
            return True
        return False
