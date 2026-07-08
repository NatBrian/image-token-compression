"""Vision-model allowlist. Only models known to read rendered text get compressed."""
from __future__ import annotations

from .config import Settings


def model_supported(model: str | None, settings: Settings) -> bool:
    return settings.model_supported(model)
