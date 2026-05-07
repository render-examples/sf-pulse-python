"""HTTP fetch helpers and DuckDuckGo search — port of bin/cron-refresh/http.ts.

Provides:
- fetch_url(url): fetch a page's HTML following manual redirects (returns "" on failure).
- fetch_text(url): fetch and strip HTML to text.
- ddg_search(query, max_results): scrape DuckDuckGo HTML search results.
- set_lookup_override_for_tests(callable): replaces httpx.AsyncClient factory in tests.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx

from app.sources.constants import (
    CRON_USER_AGENT,
    FETCH_TIMEOUT_SECONDS,
    MAX_REDIRECTS,
)

LookupOverride = Callable[[str], Awaitable[str]] | None
_lookup_override: LookupOverride = None


def set_lookup_override_for_tests(override: LookupOverride) -> None:
    """Test hook: when set, fetch_url/ddg_search/fetch_rss return the override's value
    for any URL (mirrors the TS lookup-override pattern for offline tests)."""
    global _lookup_override
    _lookup_override = override


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    """Mirror of stripHtml() in html.ts: replace tags with spaces, collapse whitespace, slice 8000."""
    cleaned = _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()
    return cleaned[:8000]


_NOISE_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_NOISE_BLOCK_RE = re.compile(
    r"<(?:script|style|svg|noscript|nav|footer)\b[\s\S]*?</(?:script|style|svg|noscript|nav|footer)>",
    re.IGNORECASE,
)
_SEMANTIC_RE = re.compile(
    r"<(?:article|main)\b[^>]*>([\s\S]*?)</(?:article|main)>", re.IGNORECASE
)


def strip_parsing_noise_html(html: str) -> str:
    cleaned = _NOISE_COMMENT_RE.sub(" ", html)
    return _NOISE_BLOCK_RE.sub(" ", cleaned)


def extract_body_text(html: str, limit: int = 8_000) -> str:
    cleaned = strip_parsing_noise_html(html)
    semantic = _SEMANTIC_RE.search(cleaned)
    content = semantic.group(1) if semantic else cleaned
    return strip_html(content)[:limit]


def _client(**kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": CRON_USER_AGENT},
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
        **kwargs,
    )


async def fetch_url(url: str, *, timeout: float | None = None) -> str:  # noqa: ASYNC109
    """Fetch HTML at url, following up to MAX_REDIRECTS redirects manually.
    Returns "" on any failure (mirrors TS swallow-and-return behaviour)."""
    if _lookup_override is not None:
        try:
            return await _lookup_override(url)
        except Exception:
            return ""

    timeout_value = timeout if timeout is not None else FETCH_TIMEOUT_SECONDS

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": CRON_USER_AGENT},
            timeout=timeout_value,
            follow_redirects=False,
        ) as client:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                response = await client.get(current)
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        return ""
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    return ""
                return response.text
            return ""
    except Exception:
        return ""


async def fetch_text(url: str) -> str:
    html = await fetch_url(url)
    return strip_html(html) if html else ""


async def ddg_search(query: str, max_results: int = 20) -> str:
    """Fetch DuckDuckGo HTML search result page for a query.
    Returns the raw HTML response; callers parse links/text as needed.
    Returns "" on failure."""
    _ = max_results  # currently unused; HTML page is fixed-size per query
    target = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    return await fetch_url(target)


_DDG_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>',
    re.IGNORECASE,
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)</a>',
    re.IGNORECASE,
)
_DDG_UDDG_RE = re.compile(r"uddg=([^&\"'\s>]+)")


def parse_ddg_results(html: str) -> list[dict[str, str]]:
    """Extract result link/title/snippet triples from a DuckDuckGo HTML page."""
    from urllib.parse import unquote

    results: list[dict[str, str]] = []
    links = _DDG_RESULT_LINK_RE.findall(html)
    snippets = _DDG_SNIPPET_RE.findall(html)
    for index, (href, title_html) in enumerate(links):
        url = href
        match = _DDG_UDDG_RE.search(href)
        if match:
            try:
                url = unquote(match.group(1))
            except Exception:
                url = href
        snippet_html = snippets[index] if index < len(snippets) else ""
        results.append(
            {
                "url": url,
                "title": strip_html(title_html),
                "snippet": strip_html(snippet_html),
            }
        )
    return results
