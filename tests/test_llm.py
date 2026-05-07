"""LLM extraction module tests — uses an injected fake client."""

from __future__ import annotations

from app.llm import (
    RawArticle,
    extract_restaurants_from_articles,
    get_llm_client,
    set_llm_client_for_tests,
)
from app.llm.schemas import ExtractedRestaurant, RestaurantExtraction


async def test_get_llm_client_returns_none_without_api_key() -> None:
    # Fixture-free path: no LLM_API_KEY in test env → graceful None.
    set_llm_client_for_tests(None)
    try:
        from app.config import get_settings

        get_settings.cache_clear()
        client = get_llm_client()
        assert client is None
    finally:
        get_settings.cache_clear()


async def test_set_llm_client_for_tests_overrides_factory(mock_llm) -> None:
    assert get_llm_client() is mock_llm


async def test_extract_restaurants_from_articles_passes_articles_through(
    mock_llm,
) -> None:
    mock_llm.queue(
        RestaurantExtraction(
            restaurants=[
                ExtractedRestaurant(
                    name="Joe's",
                    neighborhood="Mission",
                    cuisine="Pizza",
                    opened_date="April 15, 2026",
                    address=None,
                )
            ]
        )
    )

    articles = [
        RawArticle(
            source="eater",
            url="https://example.com/a",
            title="New SF restaurant",
            bodyText="Joe's opens in the Mission",
            pubDate=None,
        )
    ]
    out = await extract_restaurants_from_articles(mock_llm, articles)
    assert len(out) == 1
    assert out[0].name == "Joe's"
    assert out[0].source_url == "https://example.com/a"
    # Verify the call was made with our prompt and that the article body is in the text.
    assert len(mock_llm.calls) == 1
    assert "Joe's opens in the Mission" in mock_llm.calls[0]["text"]


async def test_extract_restaurants_empty_articles_short_circuits(mock_llm) -> None:
    out = await extract_restaurants_from_articles(mock_llm, [])
    assert out == []
    assert mock_llm.calls == []


async def test_extract_restaurants_swallows_errors_and_returns_empty(mock_llm) -> None:
    # Both the initial call and the retry raise → extract_structured returns None.
    mock_llm.queue(RuntimeError("boom"))
    mock_llm.queue(RuntimeError("still broken"))

    articles = [
        RawArticle(
            source="eater",
            url="https://example.com/a",
            title="t",
            bodyText="b",
            pubDate=None,
        )
    ]
    out = await extract_restaurants_from_articles(mock_llm, articles)
    assert out == []
