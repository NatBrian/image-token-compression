"""CLI: `python -m imgctx serve|stats|watch|version`."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from . import __version__
from .config import load_settings

# Optional: well-known model pricing (USD per 1M tokens).
# Populated by --pricing or a PRICING_JSON / IMGCTX_PRICING env var.
# Structure: {model: {input, output, cache_read}}. All per-1M-tokens.
_DEFAULT_PRICING: dict[str, dict[str, float]] = {}


def _load_pricing(pricing_arg: str | None) -> dict:
    if pricing_arg:
        p = Path(pricing_arg)
        return json.loads(p.read_text()) if p.exists() else json.loads(pricing_arg)
    env = os.environ.get("PRICING_JSON") or os.environ.get("IMGCTX_PRICING") or ""
    if env:
        p = Path(env)
        return json.loads(p.read_text()) if p.exists() else json.loads(env)
    return dict(_DEFAULT_PRICING)


def _maybe_cost(m: str, kind: str, tokens: float, pricing: dict) -> str:
    """Return cost string or empty if no pricing for this model."""
    rates = pricing.get(m) or pricing.get("default") or {}
    rate = rates.get(kind, 0)
    if not rate:
        return ""
    return f"${tokens * rate / 1_000_000:.4f}"


def _real_cache_write(u: dict, is_anthropic: bool) -> int:
    """Cache-WRITE tokens, checked across every shape seen in the wild so far.
    There is no universal field name across providers: Anthropic, OpenAI-style
    gateways, and multiplexing gateways (e.g. an OpenAI-shaped response that's
    actually proxying a Claude backend) each use a different key. This list grows
    as new gateways surface new names; it is not, and cannot be, exhaustive."""
    if is_anthropic:
        return u.get("cache_creation_input_tokens", 0) or 0
    # Chat Completions nests cache under prompt_tokens_details; the native Responses
    # API (codex / opencode-OAuth relay) nests it under input_tokens_details instead.
    det = u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}
    return (
        det.get("cache_write_tokens", 0) or 0
        or u.get("cache_write_tokens", 0) or 0
        or (u.get("claude_cache_creation_5_m_tokens", 0) or 0)
        + (u.get("claude_cache_creation_1_h_tokens", 0) or 0)
    )


def _real_cache_read(u: dict, is_anthropic: bool) -> int:
    """Cache-READ tokens across usage shapes. Anthropic reports it top-level; Chat
    Completions nests it under prompt_tokens_details; the native Responses API
    (codex / opencode-OAuth relay) nests it under input_tokens_details."""
    if is_anthropic:
        return u.get("cache_read_input_tokens", 0) or 0
    det = u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}
    return det.get("cached_tokens", 0) or 0


def _real_cost(u: dict) -> float | None:
    """A provider-reported dollar cost, if this endpoint sends one (e.g. OpenRouter's
    usage.cost). None means "not reported", never "zero"; do not conflate with a
    genuinely free call."""
    c = u.get("cost")
    return float(c) if c is not None else None


def _region_abbrev(regions: dict[str, int]) -> str:
    parts = []
    for r in ("tools", "system", "user_text", "history"):
        if regions.get(r, 0):
            parts.append(r.replace("user_text", "user").replace("tools", "tool"))
    return "+".join(parts) if parts else "none"


def _human_dur(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms/1000:.1f}s"
    return f"{ms/60000:.0f}m{ms%60000/1000:.0f}s"


def _serve(args) -> int:
    import uvicorn

    from .proxy import build_app

    settings = load_settings()
    if args.port:
        settings.port = args.port
    if args.host:
        settings.host = args.host
    if args.upstream:
        settings.upstream_base = args.upstream.rstrip("/")
    app = build_app(settings)
    print(f"imgctx v{__version__} proxy on http://{settings.host}:{settings.port}", file=sys.stderr)
    print(f"  -> upstream {settings.upstream_base}", file=sys.stderr)
    print(f"  -> compressing for models matching {settings.model_allowlist}", file=sys.stderr)
    if settings.openai_oauth:
        print(f"  -> OpenAI OAuth relay enabled (reading tokens from {settings.openai_credentials_path})", file=sys.stderr)
    if settings.codex_oauth:
        print(f"  -> Codex CLI OAuth relay enabled (reading tokens from {settings.codex_credentials_path})", file=sys.stderr)
    print(f"  point your CLI's provider baseURL at http://{settings.host}:{settings.port}/v1", file=sys.stderr)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    return 0


def _stats(args) -> int:
    settings = load_settings()
    path = Path(args.path or settings.log_path)
    if not path.exists():
        print(f"no event log at {path}", file=sys.stderr)
        return 1
    n = 0
    compressed = 0
    text_tok = 0.0
    img_tok = 0.0
    regions: dict[str, int] = defaultdict(int)
    real_prompt = 0
    for line in path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        n += 1
        t = ev.get("transform")
        if t and t.get("compressed"):
            compressed += 1
            text_tok += t.get("est_text_tokens", 0)
            img_tok += t.get("est_image_tokens", 0)
            for r, c in (t.get("regions") or {}).items():
                regions[r] += c
        u = ev.get("usage") or {}
        real_prompt += u.get("prompt_tokens", 0) or 0
    saved = text_tok - img_tok
    print(f"events: {n}  compressed: {compressed}")
    print(f"estimated imaged-region text tokens : {text_tok:,.0f}")
    print(f"estimated image tokens              : {img_tok:,.0f}")
    print(f"estimated tokens saved              : {saved:,.0f}"
          + (f"  ({100*saved/text_tok:.0f}% of imaged region)" if text_tok else ""))
    print(f"regions imaged                      : {dict(regions)}")
    print(f"total upstream-billed prompt tokens : {real_prompt:,}")
    return 0


def _watch(args) -> int:
    settings = load_settings()
    path = Path(args.path or settings.log_path)
    pricing = _load_pricing(args.pricing)
    # Show the COST column whenever we might have a number for it: either the user
    # supplied --pricing for simulation, or we simply don't know yet and a provider
    # might self-report real cost per-call (only discoverable once events arrive).
    show_cost = True

    # Column layout
    COLS = [
        ("TIME",      8,  "<"),
        ("MODEL",     28, "<"),
        ("INPUT",     10, ">"),
        ("OUTPUT",    10, ">"),
        ("SAVED",     10, ">"),
        ("IMAGES",    7,  ">"),
        ("CACHE-R",   9,  ">"),
        ("CACHE-W",   9,  ">"),
        ("DURATION",  9,  ">"),
        ("AREAS",     24, "<"),
    ]
    if show_cost:
        COLS.append(("COST", 10, ">"))
    hdr_fmt = "  ".join(f"{{:{a}{w}}}" for _, w, a in COLS)
    H = [c[0] for c in COLS]
    sep = "  ".join("─" * w for _, w, _ in COLS)

    print(hdr_fmt.format(*H))
    print(sep)

    # Running totals
    class Tot:
        n = compressed = prompt = comp = cache = cache_w = imgs = 0
        text_tok = img_tok = saved = dur = real_cost = 0.0
        has_real_cost = False

    tot = Tot()

    def emit(ev: dict, newline: bool = True):
        ts = ev.get("ts", 0)
        model = ev.get("model") or "-"
        status = ev.get("status", 0)
        dur = ev.get("duration_ms", 0)
        u = ev.get("usage") or {}
        t = ev.get("transform")
        is_anthropic = ev.get("path", "").endswith("/v1/messages")
        # Normalise usage keys across API formats.
        # OpenAI : prompt_tokens / completion_tokens / prompt_tokens_details.cached_tokens
        # Anthropic: input_tokens / output_tokens / cache_read_input_tokens (top-level)
        ptok = u.get("prompt_tokens") or u.get("input_tokens") or 0
        ctok = u.get("completion_tokens") or u.get("output_tokens") or 0
        cache_r = _real_cache_read(u, is_anthropic)
        cache_w = _real_cache_write(u, is_anthropic)
        real_cost = _real_cost(u)
        imgs = t.get("image_count", 0) if t else 0
        text_tok = img_tok = 0.0
        if t and t.get("compressed"):
            img_tok = t.get("est_image_tokens", 0)
            text_tok = t.get("est_text_tokens", 0)
        saved = int(text_tok - img_tok)
        regs = _region_abbrev((t or {}).get("regions") or {})
        lt = time.localtime(ts)
        tm = f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}"
        ml = f"{model} ({status})"
        ds = _human_dur(dur)
        row = [tm, ml, f"{ptok:,}", f"{ctok:,}", f"{saved:,}", str(imgs),
               f"{cache_r:,}", f"{cache_w:,}", ds, regs]
        if show_cost:
            cost_str = f"${real_cost:.4f}" if real_cost is not None \
                else _maybe_cost(model, "input", ptok, pricing)
            row.append(cost_str)
        if newline:
            print(hdr_fmt.format(*row))

        # Update totals
        tot.n += 1
        tot.prompt += ptok
        tot.comp += ctok
        tot.cache += cache_r
        tot.cache_w += cache_w
        tot.imgs += imgs
        tot.dur += dur
        tot.text_tok += text_tok
        tot.img_tok += img_tok
        tot.saved += saved
        if real_cost is not None:
            tot.real_cost += real_cost
            tot.has_real_cost = True
        if t and t.get("compressed"):
            tot.compressed += 1

    # Seed existing lines
    ino = None
    pos = 0
    try:
        st = path.stat()
        ino, pos = st.st_ino, st.st_size
        for line in path.read_text().splitlines():
            try:
                emit(json.loads(line), newline=False)
            except Exception:
                pass
    except FileNotFoundError:
        pass

    # Poll for new lines
    try:
        while True:
            time.sleep(0.5)
            try:
                st = path.stat()
            except FileNotFoundError:
                continue
            if st.st_ino != ino:
                ino, pos = st.st_ino, 0
                tot = Tot()
                print("\n── log rotated ──\n")
                print(hdr_fmt.format(*H))
                print(sep)
            if st.st_size <= pos:
                continue
            with open(path) as f:
                f.seek(pos)
                for line in f:
                    line = line.rstrip("\n")
                    if line:
                        try:
                            emit(json.loads(line))
                        except Exception:
                            pass
                pos = f.tell()
    except KeyboardInterrupt:
        print()
        print(sep)
        saved_pct = (100 * tot.saved / tot.text_tok) if tot.text_tok else 0
        parts = [
            f"events: {tot.n}", f"compressed: {tot.compressed}",
            f"prompt: {tot.prompt:,}", f"output: {tot.comp:,}",
            f"cache-read: {tot.cache:,}", f"cache-write: {tot.cache_w:,}",
            f"saved: {tot.saved:,.0f} tok ({saved_pct:.0f}%)",
        ]
        if tot.has_real_cost:
            parts.append(f"cost (real, provider-reported): ${tot.real_cost:.4f}")
        elif show_cost and tot.prompt:
            c = _maybe_cost("default", "input", tot.prompt, pricing)
            if c:
                parts.append(f"cost (simulated): {c}")
        print("  ".join(parts))
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="imgctx", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve", help="run the proxy")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--upstream", default=None, help="real upstream base URL")
    p_serve.set_defaults(func=_serve)

    p_stats = sub.add_parser("stats", help="summarize the event log")
    p_stats.add_argument("--path", default=None)
    p_stats.set_defaults(func=_stats)

    p_watch = sub.add_parser("watch", help="tail events in real time")
    p_watch.add_argument("--path", default=None)
    p_watch.add_argument("--pricing", default=None,
                         help="JSON file or string with model pricing")
    p_watch.set_defaults(func=_watch)

    p_ver = sub.add_parser("version")
    p_ver.set_defaults(func=lambda a: (print(__version__) or 0))

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
