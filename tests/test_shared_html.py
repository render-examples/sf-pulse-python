"""Tests for app.shared.html."""

from __future__ import annotations

from app.shared.html import (
    decode_html_entities,
    decode_html_entities_recursive,
    escape_html,
    normalize_whitespace,
)


def test_decode_named_entities() -> None:
    assert decode_html_entities("Tom &amp; Jerry") == "Tom & Jerry"
    assert decode_html_entities("&lt;b&gt;hi&lt;/b&gt;") == "<b>hi</b>"


def test_decode_decimal_entities() -> None:
    assert decode_html_entities("caf&#233;") == "café"


def test_decode_hex_entities() -> None:
    assert decode_html_entities("caf&#xE9;") == "café"


def test_decode_recursive_handles_double_encoding() -> None:
    assert decode_html_entities_recursive("&amp;amp;") == "&"


def test_decode_unknown_entity_left_alone() -> None:
    assert decode_html_entities("&unknownentity;") == "&unknownentity;"


def test_escape_html_basic() -> None:
    assert escape_html("<b>Tom & Jerry</b>") == "&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;"


def test_escape_html_keeps_existing_entities() -> None:
    # Bare ampersand becomes &amp; but already-encoded &amp; is left intact.
    assert escape_html("Tom &amp; Jerry") == "Tom &amp; Jerry"


def test_escape_html_quotes() -> None:
    assert escape_html("\"Hi\" 'there'") == "&quot;Hi&quot; &#39;there&#39;"


def test_normalize_whitespace_collapses_runs() -> None:
    assert normalize_whitespace("  a   b\n\tc  ") == "a b c"
