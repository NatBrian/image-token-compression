"""Generate the Anthropic real-cost chart for the README.

Reads REAL data only, token usage and `total_cost_usd` from each run's stream,
across four Claude Code A/B benchmarks on the SAME model (claude-sonnet-5):

  cache-heavy (imaging LOSES on cost):
    * SWE-bench Lite   long agentic loop, frozen repo re-read across many turns
    * HotpotQA         short QA over a re-read context
  non-cache-heavy (imaging WINS on cost):
    * narrativeqa      one large UNIQUE doc, read once
    * gov_report       one large UNIQUE report, summarized once

The token bar is teal everywhere (tokens always fall). The cost bar is colored by
sign, red when real dollars rise, green when they fall, so the picture reads at a
glance: cost only falls when the big context is unique and read once. No price
formula anywhere.

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
LONG = ROOT / "bench" / "longdoc_runs"
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

TOK_C = "#1f9e8a"    # teal   tokens fall (always)
UP_C = "#d1495b"     # red    dollars rise (bad)
WIN_C = "#2a9d3f"    # green  dollars fall (good)

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


def collect(results_file: Path, stream_of):
    results = json.loads(results_file.read_text())
    by_id: dict[str, dict] = {}
    for r in results:
        ident = r.get("instance_id") or r.get("qid")
        cond = r.get("cond")
        if not ident or cond not in ("off", "on"):
            continue
        evt = _last_result(stream_of(cond, ident))
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
    swe = collect(SWE / "results.json",
                  lambda c, i: SWE / c / f"{i}.stream.jsonl")
    hot = collect(HOT / "results.json",
                  lambda c, i: HOT / c / i / "stream.jsonl")
    nqa = collect(LONG / "results_narrativeqa.json",
                  lambda c, i: LONG / c / i / "stream.jsonl")
    gov = collect(LONG / "results_gov_report.json",
                  lambda c, i: LONG / c / i / "stream.jsonl")

    # order: cache-heavy losers first, non-cache-heavy winners second
    series = [
        ("SWE-bench Lite\n(agentic, re-read)", swe),
        ("HotpotQA\n(short, re-read)", hot),
        ("narrativeqa\n(unique, read once)", nqa),
        ("gov_report\n(unique, read once)", gov),
    ]
    labels = [s[0] for s in series]
    tok = [s[1][0] for s in series]
    cost = [s[1][1] for s in series]

    x = range(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9.4, 4.6))
    b1 = ax.bar([i - w / 2 for i in x], tok, w, label="input tokens", color=TOK_C)
    cost_colors = [UP_C if c > 0 else WIN_C for c in cost]
    b2 = ax.bar([i + w / 2 for i in x], cost, w, color=cost_colors)

    # divider between the two regimes
    ax.axvline(1.5, color="#bbb", linestyle="--", linewidth=1)
    ax.text(0.5, ax.get_ylim()[1], "cache-heavy: cost RISES",
            ha="center", va="top", fontsize=9.5, color=UP_C, fontweight="bold")
    ax.text(2.5, ax.get_ylim()[1], "read-once: cost FALLS",
            ha="center", va="top", fontsize=9.5, color=WIN_C, fontweight="bold")

    ax.axhline(0, color="#333", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("change ON vs OFF (%)")
    ax.set_title("Same model (claude-sonnet-5), same tool: tokens always fall, "
                 "cost falls only when the doc is read once")

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color=TOK_C, label="input tokens"),
        Patch(color=UP_C, label="real cost, rises (total_cost_usd)"),
        Patch(color=WIN_C, label="real cost, falls (total_cost_usd)"),
    ], frameon=False, loc="lower left", fontsize=9.5)

    for bars in (b1, b2):
        for r in bars:
            h = r.get_height()
            ax.annotate(f"{h:+.1f}%", (r.get_x() + r.get_width() / 2, h),
                        ha="center", va="bottom" if h >= 0 else "top",
                        xytext=(0, 3 if h >= 0 else -3), textcoords="offset points",
                        fontsize=9.5, fontweight="bold")

    allv = tok + cost
    pad = max(abs(min(allv)), abs(max(allv))) * 0.3
    ax.set_ylim(min(allv) - pad - 4, max(allv) + pad + 10)
    fig.text(0.5, -0.02,
             "All values are Claude Code's own reported usage and total_cost_usd, no price formula.",
             ha="center", fontsize=9, color="#666")
    fig.tight_layout()
    out = OUT / "anthropic_token_vs_cost.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")
    for name, (t, c) in series:
        print(f"  {name.splitlines()[0]:16s} tok {t:+6.1f}%  cost {c:+6.1f}%")


if __name__ == "__main__":
    main()
