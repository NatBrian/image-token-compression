"""CLI: `python -m imgctx serve|stats|version`."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import __version__
from .config import load_settings


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

    p_ver = sub.add_parser("version")
    p_ver.set_defaults(func=lambda a: (print(__version__) or 0))

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
