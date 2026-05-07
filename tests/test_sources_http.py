"""HTTP fetch helpers — verify lookup override pattern."""

from __future__ import annotations

import pytest

from app.sources.http import (
    extract_body_text,
    fetch_url,
    parse_ddg_results,
    set_lookup_override_for_tests,
    strip_html,
)


@pytest.fixture(autouse=True)
def _reset_override():
    yield
    set_lookup_override_for_tests(None)


async def test_lookup_override_intercepts_fetch_url() -> None:
    captured: list[str] = []

    async def fake(url: str) -> str:
        captured.append(url)
        return "<html><body>hello</body></html>"

    set_lookup_override_for_tests(fake)
    out = await fetch_url("https://example.com/article")
    assert out == "<html><body>hello</body></html>"
    assert captured == ["https://example.com/article"]


async def test_lookup_override_swallows_exceptions() -> None:
    async def boom(url: str) -> str:
        raise RuntimeError("network down")

    set_lookup_override_for_tests(boom)
    assert await fetch_url("https://example.com") == ""


def test_strip_html_removes_tags_and_collapses_whitespace() -> None:
    assert strip_html("<p>Hello   <b>world</b></p>") == "Hello world"


def test_extract_body_text_prefers_article_tag() -> None:
    html = """
        <html>
        <body>
            <nav>Menu</nav>
            <article>The article body</article>
            <footer>copyright</footer>
        </body>
        </html>
    """
    out = extract_body_text(html)
    assert "The article body" in out
    assert "Menu" not in out
    assert "copyright" not in out


def test_parse_ddg_results_extracts_links() -> None:
    html = (
        '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">'
        "Example Title</a>"
        '<a class="result__snippet" href="#">Example snippet</a>'
    )
    results = parse_ddg_results(html)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/page"
    assert results[0]["title"] == "Example Title"
    assert results[0]["snippet"] == "Example snippet"
