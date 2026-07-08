"""Shared per-token-class breakdown table for the Claude Code A/B reports.

Imaging only touches INPUT, and Anthropic prices the three input classes very
differently (fresh 1x, cache-write ~1.25-2x, cache-read ~0.1x), so a single
blended "input tokens" number hides which class actually moved, and therefore
where the dollars come from. This renders the real per-field usage with each
class broken out, plus the input-side subtotal and output (shown for
completeness, since imaging can shift verbosity even though it never compresses
output).

All values are Claude's own reported per-field usage. The only math is summation
and percent-change.
"""
from __future__ import annotations

# (usage key, human label). Order: cheapest-to-most-expensive input, then output.
FIELDS = [
    ("input_tokens", "fresh input (1x)"),
    ("cache_creation_input_tokens", "cache WRITE (~1.25-2x)"),
    ("cache_read_input_tokens", "cache read (~0.1x)"),
]
OUTPUT = ("output_tokens", "output (not compressed)")


def _pct(on: float, off: float) -> float:
    return 100.0 * (on - off) / off if off else 0.0


def _sum(usages, key) -> int:
    return sum((u.get(key, 0) or 0) for u in usages)


def breakdown_lines(off_usages, on_usages,
                    title="By token class (real per-field usage)") -> list[str]:
    """Markdown lines: per-class OFF/ON counts + change, input-side subtotal, output.

    off_usages / on_usages are lists of Claude usage dicts (one per matched item)."""
    lines = [f"### {title}", "",
             "Imaging only compresses **input**; the three input classes are priced very "
             "differently, so the class that moves is what moves the bill.", "",
             "| token class | OFF | ON | change |",
             "| --- | ---: | ---: | ---: |"]
    for key, label in FIELDS:
        o, n = _sum(off_usages, key), _sum(on_usages, key)
        lines.append(f"| {label} | {o:,} | {n:,} | **{_pct(n, o):+.1f}%** |")
    o_in = sum(_sum(off_usages, k) for k, _ in FIELDS)
    n_in = sum(_sum(on_usages, k) for k, _ in FIELDS)
    lines.append(f"| **input-side total (imaged)** | {o_in:,} | {n_in:,} "
                 f"| **{_pct(n_in, o_in):+.1f}%** |")
    ok, olabel = OUTPUT
    o_out, n_out = _sum(off_usages, ok), _sum(on_usages, ok)
    lines.append(f"| {olabel} | {o_out:,} | {n_out:,} | {_pct(n_out, o_out):+.1f}% |")
    lines += ["",
              "The bill follows the **cache-WRITE** row, not the blended total: it is the "
              "priciest input class, so its direction (down = cheaper, up = pricier) "
              "decides the real-dollar sign.", ""]
    return lines
