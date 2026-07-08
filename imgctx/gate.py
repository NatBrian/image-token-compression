"""Profitability gate: only image a block when it actually saves input tokens.

Image-token cost is proportional to pixel area, independent of how much text is
inside. Sparse prose (~4 chars/token) rarely wins; dense code/JSON/logs
(~1-2 chars/token) do. We render first (CPU only, no token cost), then compare
the *actual* pixel cost against the text-token cost and keep whichever is
cheaper. Estimates bias conservative so mispredictions leave money on the table
rather than inflating the bill.
"""
from __future__ import annotations

from .config import Settings
from .render import RenderedPage


def estimate_text_tokens(text: str, chars_per_token: float) -> float:
    if chars_per_token <= 0:
        chars_per_token = 4.0
    return len(text) / chars_per_token


def image_tokens(pages: list[RenderedPage], settings: Settings) -> float:
    ppt = settings.pixels_per_token if settings.pixels_per_token > 0 else 750.0
    total_px = sum(p.pixels for p in pages)
    return (total_px / ppt) * settings.image_cost_margin


def is_profitable(text: str, pages: list[RenderedPage], settings: Settings) -> bool:
    if not pages:
        return False
    return image_tokens(pages, settings) < estimate_text_tokens(text, settings.chars_per_token)
