"""Extract byte-exact identifiers from an imaged block and carry them as text.

Rendered images convey structure and prose well but corrupt exact strings.
For a block we decide to image, we scrape the tokens whose exact value the model
might need verbatim, file paths, hashes, UUIDs, numbers, versions, URLs, CLI
flags, error codes, and emit them as a compact deterministic plain-text sheet
that rides alongside the image. Bulk goes to pixels; exact tokens stay text.
"""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("path", re.compile(r"(?:\.{0,2}/)?[\w.\-]+(?:/[\w.\-]+)+")),
    ("url", re.compile(r"https?://[^\s'\"<>)]+")),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("hex", re.compile(r"\b[0-9a-fA-F]{12,}\b")),
    ("version", re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:[-.][A-Za-z0-9]+)*\b")),
    ("flag", re.compile(r"(?<!\w)--?[A-Za-z][\w-]{2,}")),
    ("number", re.compile(r"(?<![\w.])-?\d{4,}(?:\.\d+)?(?![\w.])")),
]
_MAX_ITEMS_PER_KIND = 40
_MAX_SHEET_CHARS = 4000


def extract_facts(text: str) -> dict[str, list[str]]:
    facts: dict[str, list[str]] = {}
    for kind, rx in _PATTERNS:
        seen: dict[str, None] = {}
        for m in rx.finditer(text):
            val = m.group(0)
            if val not in seen:
                seen[val] = None
            if len(seen) >= _MAX_ITEMS_PER_KIND:
                break
        if seen:
            facts[kind] = list(seen.keys())
    return facts


def build_factsheet(text: str) -> str:
    """Return a compact text block of exact tokens, or '' if none worth carrying."""
    facts = extract_facts(text)
    if not facts:
        return ""
    lines = ["[exact tokens from the image above, verbatim]"]
    for kind, vals in facts.items():
        joined = " ".join(vals)
        lines.append(f"{kind}: {joined}")
    sheet = "\n".join(lines)
    if len(sheet) > _MAX_SHEET_CHARS:
        sheet = sheet[:_MAX_SHEET_CHARS] + " …"
    return sheet
