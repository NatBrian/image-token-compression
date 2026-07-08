"""Verbatim-safety predicate: which text blocks must stay as text.

Rendered text is read by a vision encoder, not an OCR engine, so exact-string
recall (hashes, UUIDs, long hex, secrets) is unreliable and fails *silently*.
A block that is short, or dense with byte-exact identifiers, is pinned as text.
The complementary factsheet module rescues stray identifiers from blocks that
are still imaged.
"""
from __future__ import annotations

import re

# Long byte-exact tokens whose exact value matters and mis-reads silently.
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|-----BEGIN)")
_BASE64_BLOB = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def identifier_density(text: str) -> float:
    """Fraction of chars that belong to byte-exact identifiers."""
    if not text:
        return 0.0
    matched = 0
    for rx in (_UUID, _LONG_HEX, _SECRET, _BASE64_BLOB):
        for m in rx.finditer(text):
            matched += len(m.group(0))
    return matched / len(text)


def should_keep_sharp(text: str, min_chars: int) -> bool:
    """True => keep this block as text (do not image it)."""
    if len(text) < min_chars:
        return True
    if _SECRET.search(text):
        return True
    # If a meaningful share of the block is exact identifiers, keep it text.
    return identifier_density(text) >= 0.12
