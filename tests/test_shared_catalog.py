"""Tests for app.shared.catalog."""

from __future__ import annotations

from app.shared.catalog import (
    derive_event_category,
    derive_event_neighborhood,
    event_matches_push_preferences,
    group_by_neighborhood,
    normalize_push_preferences,
    restaurant_matches_push_preferences,
)
from app.shared.types import PushPreferences, Restaurant, SFEvent


def _restaurant(**overrides) -> Restaurant:
    base = {
        "id": 1,
        "name": "Joe's",
        "neighborhood": "Mission",
        "cuisine": "Pizza",
        "address": None,
        "opened_date": "May 1, 2026",
        "opened_start_date": "2026-05-01",
        "opened_end_date": "2026-05-31",
        "opened_date_precision": "month",
        "is_upcoming": False,
        "highlight_kind": "opening",
        "source_url": None,
    }
    base.update(overrides)
    return Restaurant.model_validate(base)


def _event(**overrides) -> SFEvent:
    base = {
        "id": 1,
        "title": "SF Jazz Festival",
        "location": "SoMa",
        "date": "August 1, 2026",
        "start_date": "2026-08-01",
        "end_date": "2026-08-01",
        "date_precision": "day",
        "is_upcoming": True,
        "dedupe_key": "k",
        "time": None,
        "description": "Jazz concert",
        "source_url": None,
    }
    base.update(overrides)
    return SFEvent.model_validate(base)


def test_derive_event_category_music() -> None:
    e = _event(title="Live Music Night", description="DJ set")
    assert derive_event_category(e) == "music"


def test_derive_event_category_market() -> None:
    e = _event(title="Mission Night Market", description="vendors")
    assert derive_event_category(e) == "market"


def test_derive_event_category_default_community() -> None:
    e = _event(title="Volunteer cleanup", description="help out")
    assert derive_event_category(e) == "community"


def test_derive_event_neighborhood_known() -> None:
    e = _event(location="Mission Dolores Park")
    assert derive_event_neighborhood(e) == "Mission"


def test_derive_event_neighborhood_other_sf_fallback() -> None:
    e = _event(location="Treasure Island")
    assert derive_event_neighborhood(e) == "Other SF"


def test_normalize_push_preferences_dedupes_and_sorts() -> None:
    out = normalize_push_preferences(
        {
            "neighborhoods": ["Mission", "mission ", "SoMa"],
            "cuisines": ["Pizza", "Pizza", "Thai"],
            "event_categories": ["music", "music", "bogus", "art"],
        }
    )
    assert out.neighborhoods == ["Mission", "SoMa", "mission"]
    assert out.cuisines == ["Pizza", "Thai"]
    assert out.event_categories == ["art", "music"]


def test_normalize_push_preferences_none_returns_empty() -> None:
    out = normalize_push_preferences(None)
    assert out.neighborhoods == []
    assert out.cuisines == []
    assert out.event_categories == []


def test_restaurant_matches_when_no_prefs_set() -> None:
    assert restaurant_matches_push_preferences(_restaurant(), PushPreferences()) is True


def test_restaurant_matches_neighborhood_filter() -> None:
    prefs = PushPreferences(neighborhoods=["Mission"])
    assert restaurant_matches_push_preferences(_restaurant(neighborhood="Mission"), prefs) is True
    assert restaurant_matches_push_preferences(_restaurant(neighborhood="SoMa"), prefs) is False


def test_event_matches_push_preferences_category() -> None:
    e = _event(title="Concert at Mission Dolores", description="band")
    prefs = PushPreferences(event_categories=["music"])
    assert event_matches_push_preferences(e, prefs) is True

    other = _event(title="Volunteer cleanup", description="help out", location="Mission")
    assert event_matches_push_preferences(other, prefs) is False


def test_group_by_neighborhood_buckets_correctly() -> None:
    restaurants = [_restaurant(neighborhood="Mission"), _restaurant(id=2, neighborhood="Unknown")]
    events = [_event(location="SoMa Yerba Buena"), _event(id=2, location="Treasure Island")]
    grouped = group_by_neighborhood(restaurants, events)
    assert len(grouped["Mission"].restaurants) == 1
    assert len(grouped["Other SF"].restaurants) == 1  # "Unknown" → fallback
    assert len(grouped["Other SF"].events) == 1
    # SoMa wins over Yerba Buena because SoMa is checked first.
    assert len(grouped["SoMa"].events) == 1
