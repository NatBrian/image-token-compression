"""Central configuration, all overridable by environment variables.

imgctx is a transparent, OpenAI-compatible proxy that renders bulky text
context into images before forwarding to a vision-capable model, cutting input
tokens while preserving agent behavior.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_FONT = str(ASSETS_DIR / "DejaVuSans.ttf")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    raw = raw.strip()
    if not raw:
        return list(default)
    if raw.lower() in ("off", "none"):
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass
class Settings:
    # --- networking ---
    host: str = field(default_factory=lambda: os.environ.get("IMGCTX_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("IMGCTX_PORT", 8787))
    # Real upstream base (OpenAI-compatible). Default: OpenCode Zen gateway.
    upstream_base: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_UPSTREAM_BASE", "https://opencode.ai/zen/v1"
        ).rstrip("/")
    )
    # Optional Authorization override. Empty => pass client's header through untouched.
    upstream_key: str = field(default_factory=lambda: os.environ.get("IMGCTX_UPSTREAM_KEY", ""))
    request_timeout: float = field(default_factory=lambda: _env_float("IMGCTX_TIMEOUT", 600.0))

    # --- Anthropic Messages API (native Claude Code protocol) ---
    # Requests to .../v1/messages are treated as Anthropic-native and forwarded here.
    anthropic_upstream_base: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_ANTHROPIC_UPSTREAM", "https://api.anthropic.com"
        ).rstrip("/")
    )
    # Claude Code strips its subscription credential from any non-canonical host, so
    # to relay a subscription we re-inject the locally stored OAuth bearer. Read at
    # forward time so token refreshes by Claude Code are picked up automatically.
    anthropic_oauth_inject: bool = field(
        default_factory=lambda: _env_bool("IMGCTX_ANTHROPIC_OAUTH_INJECT", True)
    )
    anthropic_credentials_path: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_ANTHROPIC_CREDENTIALS", str(Path.home() / ".claude" / ".credentials.json")
        )
    )
    # Mark the static system+tools image cacheable (one ephemeral breakpoint) so the
    # big fixed context is cache-read on turns 2+ instead of re-billed.
    anthropic_cache_images: bool = field(
        default_factory=lambda: _env_bool("IMGCTX_ANTHROPIC_CACHE_IMAGES", True)
    )

    # --- OpenAI OAuth relay (for opencode ChatGPT subscription) ---
    openai_oauth: bool = field(
        default_factory=lambda: _env_bool("IMGCTX_OPENAI_OAUTH", False)
    )
    openai_credentials_path: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_OPENAI_CREDENTIALS",
            str(Path.home() / ".local" / "share" / "opencode" / "auth.json")
        )
    )
    openai_oauth_upstream_base: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_OPENAI_OAUTH_UPSTREAM",
            "https://chatgpt.com/backend-api/codex"
        ).rstrip("/")
    )

    # --- master switches ---
    enabled: bool = field(default_factory=lambda: _env_bool("IMGCTX_ENABLED", True))
    # Which context regions to compress.
    compress_tool_results: bool = field(
        default_factory=lambda: _env_bool("IMGCTX_TOOL_RESULTS", True)
    )
    compress_user_text: bool = field(default_factory=lambda: _env_bool("IMGCTX_USER_TEXT", True))
    compress_system: bool = field(default_factory=lambda: _env_bool("IMGCTX_SYSTEM", True))
    compress_tools: bool = field(default_factory=lambda: _env_bool("IMGCTX_TOOLS", True))
    compress_history: bool = field(default_factory=lambda: _env_bool("IMGCTX_HISTORY", True))
    # History collapse: keep the last N messages as text; freeze the older closed
    # prefix into byte-stable, cacheable image chunks.
    history_keep_tail: int = field(default_factory=lambda: _env_int("IMGCTX_HISTORY_KEEP_TAIL", 6))
    history_min_prefix: int = field(default_factory=lambda: _env_int("IMGCTX_HISTORY_MIN_PREFIX", 6))
    history_freeze_chunk: int = field(default_factory=lambda: _env_int("IMGCTX_HISTORY_FREEZE_CHUNK", 6))

    # --- model allowlist ---
    # Base model ids (substring match) known to read rendered text. Empty => compress nothing.
    model_allowlist: list[str] = field(
        default_factory=lambda: _env_list("IMGCTX_MODELS", ["mimo", "gemini", "gpt-4", "gpt-5", "qwen", "glm", "claude", "haiku", "sonnet", "opus"])
    )

    # --- thresholds ---
    # Per-region minimum chars before a block is eligible. Below these, per-image
    # cost dominates and imaging loses tokens, so the block stays text.
    min_tool_result_chars: int = field(default_factory=lambda: _env_int("IMGCTX_MIN_TOOL_RESULT_CHARS", 6000))
    min_user_text_chars: int = field(default_factory=lambda: _env_int("IMGCTX_MIN_USER_TEXT_CHARS", 6000))
    min_system_chars: int = field(default_factory=lambda: _env_int("IMGCTX_MIN_SYSTEM_CHARS", 2000))
    # Don't touch the request unless total compressible chars exceed this.
    min_total_chars: int = field(default_factory=lambda: _env_int("IMGCTX_MIN_TOTAL_CHARS", 2000))
    # Conservative chars/token used to estimate the text-side cost in the gate.
    chars_per_token: float = field(default_factory=lambda: _env_float("IMGCTX_CHARS_PER_TOKEN", 4.0))
    # Estimated image tokens per pixel divisor (~ patch size). Calibrated by the
    # A/B harness against the real model; 750 is a safe Anthropic-like default.
    pixels_per_token: float = field(default_factory=lambda: _env_float("IMGCTX_PIXELS_PER_TOKEN", 750.0))
    # Safety margin applied to image-token estimate (bias toward passthrough).
    image_cost_margin: float = field(default_factory=lambda: _env_float("IMGCTX_IMAGE_MARGIN", 1.15))
    # Hard cap on images per single block (paging). A coding agent's tool schemas
    # alone render to ~13 pages, so this must be generous while staying under the
    # provider's per-request image limit (Anthropic allows up to 100).
    max_images_per_block: int = field(default_factory=lambda: _env_int("IMGCTX_MAX_IMAGES_PER_BLOCK", 24))
    # Global cap on images per request.
    max_images_per_request: int = field(default_factory=lambda: _env_int("IMGCTX_MAX_IMAGES", 60))

    # --- rendering ---
    font_path: str = field(default_factory=lambda: os.environ.get("IMGCTX_FONT", DEFAULT_FONT))
    cjk_font_path: str = field(default_factory=lambda: os.environ.get("IMGCTX_CJK_FONT", ""))
    dpi: int = field(default_factory=lambda: _env_int("IMGCTX_DPI", 96))
    font_size: float = field(default_factory=lambda: _env_float("IMGCTX_FONT_SIZE", 9.0))
    line_height: float = field(default_factory=lambda: _env_float("IMGCTX_LINE_HEIGHT", 10.0))
    # Cap each rendered PNG at this many pixels so vision encoders don't downscale.
    max_pixels_per_image: int = field(default_factory=lambda: _env_int("IMGCTX_MAX_PIXELS", 1_000_000))
    # Visible newline marker so the model distinguishes real newlines from soft wraps.
    newline_marker: bool = field(default_factory=lambda: _env_bool("IMGCTX_NEWLINE_MARKER", True))
    image_detail: str = field(default_factory=lambda: os.environ.get("IMGCTX_IMAGE_DETAIL", "high"))

    # --- safety ---
    keep_sharp: bool = field(default_factory=lambda: _env_bool("IMGCTX_KEEP_SHARP", True))
    factsheet: bool = field(default_factory=lambda: _env_bool("IMGCTX_FACTSHEET", True))

    # --- logging ---
    log_events: bool = field(default_factory=lambda: _env_bool("IMGCTX_LOG", True))
    log_path: str = field(
        default_factory=lambda: os.environ.get(
            "IMGCTX_LOG_PATH", str(Path.home() / ".imgctx" / "events.jsonl")
        )
    )
    # Dump full request bodies (Phase-0 instrumentation). Off by default.
    capture_dir: str = field(default_factory=lambda: os.environ.get("IMGCTX_CAPTURE_DIR", ""))

    def model_supported(self, model: str | None) -> bool:
        if not model or not self.model_allowlist:
            return False
        m = model.lower()
        return any(base.lower() in m for base in self.model_allowlist)


def load_settings() -> Settings:
    return Settings()
