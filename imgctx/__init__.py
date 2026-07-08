"""imgctx, a transparent image-context compression proxy for agentic coding CLIs.

Renders bulky text context (tool output, large pastes, system prompt) into
images before forwarding to a vision-capable model, cutting input tokens while
preserving tool calls and multi-turn behavior.
"""
from .config import Settings, load_settings
from .transform import transform_request, TransformStats
from .render import render_text_to_pages

__version__ = "0.1.0"
__all__ = [
    "Settings",
    "load_settings",
    "transform_request",
    "TransformStats",
    "render_text_to_pages",
    "__version__",
]
