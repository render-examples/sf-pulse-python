"""HTML utilities — port of shared/html.ts."""

from __future__ import annotations

import re

NAMED_ENTITIES = {
    "amp": "&",
    "apos": "'",
    "gt": ">",
    "lt": "<",
    "nbsp": " ",
    "quot": '"',
}

_ENTITY_RE = re.compile(r"&([a-zA-Z][a-zA-Z0-9]+|#\d+|#x[0-9a-fA-F]+);")
_HEX_RE = re.compile(r"^#x([0-9a-fA-F]+)$")
_DEC_RE = re.compile(r"^#(\d+)$")
_BARE_AMP_RE = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]+|#\d+|#x[a-fA-F0-9]+);)")


def _decode_numeric(entity: str) -> str | None:
    hex_match = _HEX_RE.match(entity)
    if hex_match:
        try:
            return chr(int(hex_match.group(1), 16))
        except (ValueError, OverflowError):
            return None

    dec_match = _DEC_RE.match(entity)
    if dec_match:
        try:
            return chr(int(dec_match.group(1), 10))
        except (ValueError, OverflowError):
            return None
    return None


def decode_html_entities(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        entity = match.group(1)
        named = NAMED_ENTITIES.get(entity.lower())
        if named is not None:
            return named
        decoded = _decode_numeric(entity)
        return decoded if decoded is not None else match.group(0)

    return _ENTITY_RE.sub(replace, value)


def decode_html_entities_recursive(value: str) -> str:
    current = value
    for _ in range(5):
        nxt = decode_html_entities(current)
        if nxt == current:
            break
        current = nxt
    return current


def escape_html(value: str) -> str:
    return (
        _BARE_AMP_RE.sub("&amp;", value)
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_escaped_html_text(value: str) -> str:
    return escape_html(
        normalize_whitespace(decode_html_entities_recursive(value).replace(" ", " "))
    )
