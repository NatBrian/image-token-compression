"""Render the FINAL_REPORT charts as PNGs (matplotlib) into bench/charts/.

These charts are STORY-first: each answers ONE question a reader of the summary table has,
instead of plotting every Agent×Model×Bench×Region row (that was unreadable).

  chart1_token_vs_cost_quadrant  -> Q: "does cutting tokens cut cost?"  (whole dataset, one
                                     scatter; almost all points cut tokens, but a cluster
                                     still costs MORE, the trap.)
  chart2_why_cost_rises          -> Q: "why can cost go UP when tokens go DOWN?"  (one
                                     Anthropic case, cost broken into fresh/read/write/output
                                     USD, OFF vs ON: the cache-WRITE slice balloons.)
  chart3_region_decision         -> Q: "what should I turn on?"  (same model+task, imaging
                                     the cached prefix vs imaging only the unique content,
                                     plain words, not bit strings.)

Numbers come from bench.generate_final_report.prepare_groups(), the SAME grouped values as
the report tables, so charts and text cannot disagree. Nothing is rerun.

Run:  .venv/bin/python -m bench.make_final_charts
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

from bench.generate_final_report import (
    RATES, cost_delta, input_delta, prepare_groups,
)

OUT = Path("bench/charts")
RED, GREEN, BLUE, PURPLE, GREY = "#c62828", "#2e7d32", "#1565c0", "#6a1b9a", "#9e9e9e"

# Task shape: read-once single document vs multi-turn agent loop.
READ_ONCE = {"gov_report", "narrativeqa"}


def short_model(m):
    return {"claude-sonnet": "sonnet", "claude-haiku": "haiku", "mimo-v2.5-free": "mimo",
            "gpt-5.4-mini": "gpt-5.4-mini", "gpt-4o-mini": "gpt-4o-mini",
            "gemini-3.1-flash-lite": "gemini"}.get(m, m)


def by_key(groups):
    return {(g["bench"], g["cli"], g["model"], g["bits"]): g for g in groups}


# --------------------------------------------------------------------------- #
def chart1_quadrant(groups):
    """Scatter: x = Δ input tokens, y = Δ cost. Quadrants tell the story at a glance."""
    fig, ax = plt.subplots(figsize=(10, 7.5))

    # quadrant shading: left half = tokens fell. top-left = TRAP (cost rose anyway),
    # bottom-left = WIN (cost fell too).
    ax.axhspan(0, 200, xmin=0, xmax=0.5, color=RED, alpha=0.05)
    ax.axhspan(-100, 0, xmin=0, xmax=0.5, color=GREEN, alpha=0.06)

    labelled = {  # curated outliers worth naming (key -> short label)
        ("hotpot", "Claude Code", "claude-haiku", "0·1·1·1·1"): "Claude haiku hotpot\n(image everything)",
        ("swebench", "OpenCode", "mimo-v2.5-free", "0·1·1·1·1"): "mimo swebench\n(loop, output blows up)",
        ("swebench", "Claude Code", "claude-sonnet", "0·1·1·1·1"): "Claude swebench\n(image cached prefix)",
        ("gov_report", "OpenCode", "mimo-v2.5-free", "1·1·1·1·1"): "mimo gov_report\n(read-once doc)",
        ("gov_report", "Claude Code", "claude-sonnet", "0·0·1·1·1"): "Claude gov_report\n(image doc only)",
        ("narrativeqa", "OpenCode", "mimo-v2.5-free", "0·0·1·1·1"): "mimo narrativeqa\n(doc only)",
    }
    K = by_key(groups)

    for g in groups:
        x, y = input_delta(g), cost_delta(g)[0]
        if x is None or y is None:
            continue
        fam_red = g["family"] == "anthropic"
        color = RED if fam_red else GREEN
        marker = "o" if g["bench"] in READ_ONCE else "^"  # circle=doc, triangle=loop
        ax.scatter(x, y, s=90, color=color, marker=marker, edgecolor="black",
                   linewidth=0.6, alpha=0.9, zorder=3)

    for key, lab in labelled.items():
        g = K.get(key)
        if not g:
            continue
        x, y = input_delta(g), cost_delta(g)[0]
        if x is None or y is None:
            continue
        dy = 12 if y >= 0 else -12
        ax.annotate(lab, (x, y), textcoords="offset points", xytext=(6, dy),
                    fontsize=7.2, ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))

    ax.axhline(0, color="black", lw=1)
    ax.axvline(0, color="black", lw=1)
    ax.set_xlabel("Δ input tokens (ON vs OFF, %)  ←  fewer tokens")
    ax.set_ylabel("Δ cost (ON vs OFF, %)   ↑ costs MORE / ↓ costs LESS")
    ax.set_title("Chart 1: Does cutting tokens cut cost?  Not always.\n"
                 "Almost every point is LEFT of 0 (imaging cut input tokens), but the points "
                 "in the\nred zone cut tokens AND still cost MORE. Saving tokens ≠ saving money.",
                 fontsize=10.5)
    ax.text(-52, 90, "TRAP: fewer tokens,\nbut BILL WENT UP", color=RED, fontsize=9,
            ha="center", va="center", fontweight="bold")
    ax.text(-52, -55, "WIN: fewer tokens\nAND cheaper", color=GREEN, fontsize=9,
            ha="center", va="center", fontweight="bold")

    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], marker="o", color="w", markerfacecolor=RED, markeredgecolor="black",
                  markersize=9, label="Anthropic (charges for cache writes)"),
           Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markeredgecolor="black",
                  markersize=9, label="free-write (OpenAI / mimo / gemini)"),
           Line2D([0], [0], marker="o", color="w", markerfacecolor=GREY, markeredgecolor="black",
                  markersize=9, label="○ read-once doc task"),
           Line2D([0], [0], marker="^", color="w", markerfacecolor=GREY, markeredgecolor="black",
                  markersize=9, label="△ multi-turn agent loop")]
    ax.legend(handles=leg, loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(True, ls=":", alpha=0.35)
    ax.set_xlim(-85, 105)
    fig.tight_layout()
    fig.savefig(OUT / "chart1_token_vs_cost_quadrant.png", dpi=140)
    plt.close(fig)


def _anthropic_cost_split(arm):
    """Per-class cost (USD) for an Anthropic arm, from its token split × sonnet rates."""
    fr, cw, cr, ou, _ = RATES["anthropic_sonnet"]  # (fresh, cache_write, cache_read, output)
    return {
        "fresh input": arm["fresh"] * fr / 1e6,
        "cache READ (cheap)": arm["cache_read"] * cr / 1e6,
        "cache WRITE (expensive)": arm["cache_write"] * cw / 1e6,
        "output": arm["output"] * ou / 1e6,
    }


def chart2_why_cost_rises(groups):
    """Stacked cost composition OFF vs ON for one Anthropic 'trap' case."""
    K = by_key(groups)
    g = K.get(("hotpot", "Claude Code", "claude-sonnet", "0·1·1·1·1"))
    if not g:
        return
    off = _anthropic_cost_split(g["off"])
    on = _anthropic_cost_split(g["on"])
    classes = ["fresh input", "cache READ (cheap)", "cache WRITE (expensive)", "output"]
    colors = {"fresh input": BLUE, "cache READ (cheap)": GREEN,
              "cache WRITE (expensive)": RED, "output": PURPLE}

    fig, ax = plt.subplots(figsize=(8, 6.2))
    xs = ["OFF\n(no imaging)", "ON\n(image everything)"]
    bottoms = [0.0, 0.0]
    centers = {}  # (class, arm-index) -> slice mid-height, for inline labels
    for c in classes:
        vals = [off[c], on[c]]
        ax.bar(xs, vals, bottom=bottoms, color=colors[c], label=c, edgecolor="white", lw=0.6)
        for j in (0, 1):
            centers[(c, j)] = bottoms[j] + vals[j] / 2
        bottoms = [bottoms[0] + vals[0], bottoms[1] + vals[1]]

    tot_off, tot_on = sum(off.values()), sum(on.values())
    di, dc = input_delta(g), cost_delta(g)[0]
    for i, tot in enumerate([tot_off, tot_on]):
        ax.text(i, tot + 0.03, f"total bill\n{tot:.3f} USD", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
    # inline callouts INSIDE the slices (no off-canvas annotation)
    ax.text(0, centers[("cache READ (cheap)", 0)], "big cheap\ncache-READ", ha="center",
            va="center", color="white", fontsize=8, fontweight="bold")
    ax.text(1, centers[("cache READ (cheap)", 1)], "READ\nshrinks", ha="center",
            va="center", color="white", fontsize=7.5, fontweight="bold")
    ax.text(1, centers[("cache WRITE (expensive)", 1)],
            "cache-WRITE grows\n(imaging broke the cache)", ha="center", va="center",
            color="white", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("cost for this run (USD)")
    ax.set_title("Chart 2: WHY fewer tokens can cost MORE (Claude · hotpot)\n"
                 f"Input tokens {di:+.0f}%, yet the bill {dc:+.0f}%. Imaging the cached prompt "
                 "turns\ncheap 'cache READ' (green) into expensive 'cache WRITE' (red).",
                 fontsize=10.2)
    ax.legend(fontsize=8, loc="upper left")
    ax.margins(y=0.16)
    fig.tight_layout()
    fig.savefig(OUT / "chart2_why_cost_rises.png", dpi=140)
    plt.close(fig)


def chart3_region_decision(groups):
    """Same model+task: image cached prefix vs image only unique content. Plain words."""
    K = by_key(groups)
    # (row title, provider note, aggressive-key, conservative-key)
    pairs = [
        ("Claude · hotpot", "Anthropic",
         ("hotpot", "Claude Code", "claude-sonnet", "0·1·1·1·1"),
         ("hotpot", "Claude Code", "claude-sonnet", "0·0·1·1·1")),
        ("Claude · swebench", "Anthropic",
         ("swebench", "Claude Code", "claude-sonnet", "0·1·1·1·1"),
         ("swebench", "Claude Code", "claude-sonnet", "0·0·1·0·0")),
        ("mimo · narrativeqa", "free-write",
         ("narrativeqa", "OpenCode", "mimo-v2.5-free", "1·1·1·1·1"),
         ("narrativeqa", "OpenCode", "mimo-v2.5-free", "0·0·1·1·1")),
    ]
    names = ["SYS", "TOOLS", "TOOL_RES", "USER", "HIST"]
    rows = []
    for t, _, ak, ck in pairs:
        if ak not in K or ck not in K:
            continue
        rb, gb = ak[3], ck[3]  # region bit strings, e.g. "0·1·1·1·1"
        diff = [names[i] for i, (x, y) in enumerate(zip(rb.split("·"), gb.split("·"))) if x != y]
        rows.append((t, cost_delta(K[ak])[0], cost_delta(K[ck])[0], rb, gb, diff))

    ys = [i * 1.0 for i in range(len(rows))][::-1]  # top-to-bottom
    fig, ax = plt.subplots(figsize=(11, 5.6))

    ax.axvspan(0, 45, color=RED, alpha=0.06)
    ax.axvspan(-75, 0, color=GREEN, alpha=0.06)
    ax.axvline(0, color="black", lw=1.2)

    for (t, a, c, rb, gb, diff), y in zip(rows, ys):
        ax.annotate("", xy=(c, y), xytext=(a, y),
                    arrowprops=dict(arrowstyle="-|>", lw=2.2, color=GREY, shrinkA=9, shrinkB=9))
        ax.scatter([a], [y], s=180, color=RED, edgecolor="black", zorder=4)
        ax.scatter([c], [y], s=180, color=GREEN, edgecolor="black", zorder=4)
        # % above each dot
        ax.text(a, y + 0.17, f"{a:+.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.text(c, y + 0.17, f"{c:+.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
        # ON-region config printed ON each dot's side, in plain terms
        ax.text(a + 3, y, f"regions {rb}\n(images the cached prompt)", ha="left", va="center",
                fontsize=7.3, color=RED)
        ax.text(c - 3, y, f"regions {gb}\n(prompt kept as text)", ha="right", va="center",
                fontsize=7.3, color=GREEN)
        # what actually changed, on the arrow
        ax.text((a + c) / 2, y - 0.24, f"changed: {' + '.join(diff)} → off",
                ha="center", va="top", fontsize=7.6, color="black", style="italic")

    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_ylim(-0.75, len(rows) - 0.25)
    ax.set_xlim(-78, 58)
    ax.set_xlabel("Δ cost ON vs OFF (%)      ◀ cheaper           costs more ▶")
    ax.set_title("Chart 3: What to turn ON. The ONLY thing that changes per row is the "
                 "ON-Regions config\n(order = SYS·TOOLS·TOOL_RES·USER·HIST, 1=imaged 0=text). "
                 "RED dot = also image the cached prompt;\nGREEN dot = turn those OFF, image "
                 "only unique content. Arrow = the switch that saves money.",
                 fontsize=9.6)
    ax.text(-70, len(rows) - 0.55, "SAVES", color=GREEN, fontsize=10, fontweight="bold")
    ax.text(50, len(rows) - 0.55, "COSTS MORE", color=RED, fontsize=10, fontweight="bold", ha="right")
    ax.grid(axis="x", ls=":", alpha=0.3)
    # WHY the two dots differ: the reason behind the flip
    why = ("WHY they differ:  the 'cached prompt' (system + tools + history) REPEATS every "
           "turn, so it is already cheap (cache-READ).\nImaging it changes the bytes → the "
           "cache no longer matches → you re-pay the expensive cache-WRITE (Chart 2).  The "
           "'unique\ncontent' (the document / a fresh tool result) is seen only ONCE and was "
           "never cached, so imaging it just shrinks it, for free.")
    fig.text(0.5, -0.02, why, ha="center", va="top", fontsize=8,
             bbox=dict(boxstyle="round", fc="#fff8e1", ec="#c9a227"))
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(OUT / "chart3_region_decision.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # remove the old rejected charts so the folder only holds the current set
    for old in ["chart1_input_vs_cost.png", "chart2_region_sign_flip.png",
                "chart3_price_per_bucket.png", "chart4_cost_by_family.png"]:
        p = OUT / old
        if p.exists():
            p.unlink()
    groups, _, _ = prepare_groups()
    chart1_quadrant(groups)
    chart2_why_cost_rises(groups)
    chart3_region_decision(groups)
    print(f"wrote 3 charts to {OUT}/ from {len(groups)} groups")


if __name__ == "__main__":
    main()
