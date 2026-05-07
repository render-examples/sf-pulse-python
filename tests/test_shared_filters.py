"""Tests for app.shared.filters."""

from __future__ import annotations

from app.shared.filters import (
    EventFilters,
    RestaurantFilters,
    apply_event_filters,
    apply_restaurant_filters,
    parse_home_filters,
)
from app.shared.types import Restaurant, SFEvent


def _restaurant(**overrides) -> Restaurant:
    base = {
        "id": 1,
        "name": "Joe's Pizza",
        "neighborhood": "Mission",
        "cuisine": "Pizza",
        "address": None,
        "opened_date": "April 15, 2026",
        "opened_start_date": "2026-04-15",
        "opened_end_date": "2026-04-15",
        "opened_date_precision": "day",
        "is_upcoming": False,
        "highlight_kind": "opening",
        "source_url": None,
    }
    base.update(overrides)
    return Restaurant.model_validate(base)


def _event(**overrides) -> SFEvent:
    base = {
        "id": 1,
        "title": "Outside Lands",
        "location": "Golden Gate Park",
        "date": "August 8, 2026",
        "start_date": "2026-08-08",
        "end_date": "2026-08-10",
        "date_precision": "day_range",
        "is_upcoming": True,
        "dedupe_key": "k",
        "time": None,
        "description": None,
        "source_url": None,
    }
    base.update(overrides)
    return SFEvent.model_validate(base)


def test_parse_home_filters_extracts_query_params() -> None:
    filters = parse_home_filters(
        {
            "r-q": "pizza",
            "r-neighborhood": "Mission,SoMa",
            "r-upcoming": "1",
            "e-q": "music",
            "e-category": "music,art",
            "e-from": "2026-05-01",
            "e-to": "2026-08-31",
        }
    )
    assert filters.restaurants.query == "pizza"
    assert filters.restaurants.neighborhoods == ["Mission", "SoMa"]
    assert filters.restaurants.upcoming_only is True
    assert filters.events.query == "music"
    assert filters.events.categories == ["music", "art"]
    assert filters.events.from_date == "2026-05-01"
    assert filters.events.to_date == "2026-08-31"


def test_parse_home_filters_drops_invalid_iso_date() -> None:
    filters = parse_home_filters({"r-from": "not-a-date"})
    assert filters.restaurants.from_date == ""


def test_apply_restaurant_filters_query_searches_all_fields() -> None:
    items = [
        _restaurant(id=1, name="Joe's Pizza"),
        _restaurant(id=2, name="Sushi Place", cuisine="Sushi"),
    ]
    out = apply_restaurant_filters(items, RestaurantFilters(query="pizza"))
    assert [r.id for r in out] == [1]


def test_apply_restaurant_filters_neighborhood() -> None:
    items = [
        _restaurant(id=1, neighborhood="Mission"),
        _restaurant(id=2, neighborhood="SoMa"),
    ]
    out = apply_restaurant_filters(items, RestaurantFilters(neighborhoods=["SoMa"]))
    assert [r.id for r in out] == [2]


def test_apply_restaurant_filters_combined() -> None:
    items = [
        _restaurant(id=1, neighborhood="Mission", cuisine="Pizza"),
        _restaurant(id=2, neighborhood="Mission", cuisine="Thai"),
        _restaurant(id=3, neighborhood="SoMa", cuisine="Pizza"),
    ]
    out = apply_restaurant_filters(
        items, RestaurantFilters(neighborhoods=["Mission"], cuisines=["Pizza"])
    )
    assert [r.id for r in out] == [1]


def test_apply_event_filters_date_range_overlap() -> None:
    items = [
        _event(id=1, start_date="2026-08-01", end_date="2026-08-05"),
        _event(id=2, start_date="2026-09-01", end_date="2026-09-05"),
    ]
    out = apply_event_filters(
        items, EventFilters(from_date="2026-08-04", to_date="2026-08-10")
    )
    assert [e.id for e in out] == [1]


def test_apply_event_filters_category_query_combo() -> None:
    items = [
        _event(id=1, title="Outside Lands", description="festival"),
        _event(id=2, title="Volunteer cleanup", description="community service"),
    ]
    out = apply_event_filters(items, EventFilters(query="lands"))
    assert [e.id for e in out] == [1]
