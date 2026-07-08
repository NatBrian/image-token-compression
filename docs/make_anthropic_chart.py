"""Generate the Anthropic real-cost chart for the README.

Reads REAL data only, token usage and `total_cost_usd` from each run's stream, 
for the SWE-bench and HotpotQA Claude Code A/B runs, and plots the token change
(down) beside the real-dollar change (up) for each benchmark. No price formula.

Run:  .venv/bin/python docs/make_anthropic_chart.py
Writes docs/assets/anthropic_token_vs_cost.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
SWE = ROOT / "bench" / "swebench_runs"
HOT = ROOT / "bench" / "hotpot_claude_runs"
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

DOWN_C = "#1f9e8a"  # teal  (tokens fall, good)
UP_C = "#d1495b"    # red   (dollars rise, bad)

plt.rcParams.update({
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
})


def _last_result(stream: Path):
    if not stream.exists():
        return None
    evt = None
    for line in stream.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") == "result":
            evt = e
    return evt


def _in_side(u: dict) -> int:
    return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0))


def collect(runs: Path, stream_of):
    results = json.loads((runs / "results.json").read_text())
    by_id: dict[str, dict] = {}
    for r in results:
        ident = r.get("instance_id") or r.get("qid")
        cond = r.get("cond")
        if not ident or cond not in ("off", "on"):
            continue
        evt = _last_result(stream_of(runs, cond, ident))
        u = (evt or {}).get("usage") or {}
        by_id.setdefault(ident, {})[cond] = {
            "cost": (evt or {}).get("total_cost_usd"),
            "in": _in_side(u),
            "err": bool((evt or {}).get("is_error")) or bool(r.get("harness_error")),
        }
    pairs = [(d["off"], d["on"]) for d in by_id.values()
             if "off" in d and "on" in d and not d["off"]["err"] and not d["on"]["err"]]
    toff = sum(o["in"] for o, _ in pairs)
    ton = sum(n["in"] for _, n in pairs)
    dp = [(o, n) for o, n in pairs if o["cost"] is not None and n["cost"] is not None]
    coff = sum(o["cost"] for o, _ in dp)
    con = sum(n["cost"] for _, n in dp)
    tok = 100.0 * (ton - toff) / toff if toff else 0.0
    cost = 100.0 * (con - coff) / coff if coff else 0.0
    return tok, cost


def main() -> None:
    swe_tok, swe_cost = collect(
        SWE, lambda r, c, i: r / c / f"{i}.stream.jsonl")
    hot_tok, hot_cost = collect(
        HOT, lambda r, c, i: r / c / i / "stream.jsonl")

    labels = ["SWE-bench Lite\n(long agentic)", "HotpotQA\n(short QA)"]
    tok = [swe_tok, hot_tok]
    cost = [swe_cost, hot_cost]

    x = range(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    b1 = ax.bar([i - w / 2 for i in x], tok, w, label="input tokens", color=DOWN_C)
    b2 = ax.bar([i + w / 2 for i in x], cost, w, label="real cost (total_cost_usd)", color=UP_C)

    ax.axhline(0, color="#333", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("change ON vs OFF (%)")
    ax.set_title("Claude Code (claude-sonnet-5): tokens fall, real dollars rise")
    ax.legend(frameon=False, loc="upper left")

    for bars in (b1, b2):
        for r in bars:
            h = r.get_height()
            ax.annotate(f"{h:+.1f}%", (r.get_x() + r.get_width() / 2, h),
                        ha="center", va="bottom" if h >= 0 else "top",
                        xytext=(0, 3 if h >= 0 else -3), textcoords="offset points",
                        fontsize=10, fontweight="bold")

    pad = max(abs(min(tok + cost)), abs(max(tok + cost))) * 0.25
    ax.set_ylim(min(tok + cost) - pad, max(tok + cost) + pad + 6)
    fig.text(0.5, -0.02,
             "All values are Claude Code's own reported usage and total_cost_usd, no price formula.",
             ha="center", fontsize=9, color="#666")
    fig.tight_layout()
    out = OUT / "anthropic_token_vs_cost.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}  (swe tok {swe_tok:+.1f}% cost {swe_cost:+.1f}%; "
          f"hot tok {hot_tok:+.1f}% cost {hot_cost:+.1f}%)")


if __name__ == "__main__":
    main()
