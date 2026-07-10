"""Render the README hero chart as a PNG into assets/.

ONE chart answers the two questions a first-time reader has, together:
  chart_savings.png -> "Does imaging cut input tokens, and does the bill fall with them?"

Each row is one agent x model x task, run twice (imaging off vs on) with the region-config
matched to that task. Two bars per row: input tokens removed, and cost removed. Plotting them
side by side shows the point directly: the two move together, so cutting tokens cuts dollars.

A grouped bar (not a dumbbell) is the right form here because the reader should compare two
DIFFERENT metrics per category, not a before/after gap of one metric.

Numbers come from bench.generate_final_report.prepare_groups(), the SAME grouped values as
FINAL_REPORT.md, so the README chart and the report can never disagree. Nothing is rerun.

Run:  .venv/bin/python -m bench.make_readme_charts
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

from bench.generate_final_report import prepare_groups, input_delta, cost_delta

OUT = Path("assets")

# Clean, high-contrast palette. Token bar is calm slate; cost bar is money-green so the
# "dollars" metric reads as the headline. Real provider bill gets a hatch overlay.
INK = "#1a1a2e"
MUTE = "#6b7280"
GRID = "#e5e7eb"
TOKEN_C = "#64748b"   # slate
COST_C = "#15803d"    # green

SHORT_MODEL = {"claude-sonnet": "claude-sonnet", "claude-haiku": "claude-haiku",
               "mimo-v2.5-free": "mimo", "gpt-5.4-mini": "gpt-5.4-mini",
               "gemini-3.1-flash-lite": "gemini"}
BENCH_LABEL = {"gov_report": "gov-report summary", "narrativeqa": "narrativeqa QA",
               "hotpot": "HotpotQA multihop", "swebench": "SWE-bench code-fix"}

# One row per cell, at the task-MATCHED region config (report's Quick-lookup). Only cells
# that are a clean win on BOTH metrics, so the "they move together" story is honest.
# (bench, cli, model, bits)
CELLS = [
    ("gov_report", "OpenCode", "mimo-v2.5-free", "1·1·1·1·1"),
    ("narrativeqa", "OpenCode", "mimo-v2.5-free", "0·0·1·1·1"),
    ("gov_report", "Claude Code", "claude-sonnet", "0·0·1·1·1"),
    ("swebench", "Codex", "gpt-5.4-mini", "1·1·1·1·1"),
    ("hotpot", "Codex", "gpt-5.4-mini", "1·1·1·1·1"),
    ("hotpot", "OpenCode", "mimo-v2.5-free", "1·1·1·1·1"),
    ("swebench", "Claude Code", "claude-sonnet", "0·0·1·0·0"),
    ("narrativeqa", "Codex", "gpt-5.4-mini", "1·1·1·1·1"),
    ("gov_report", "Codex", "gpt-5.4-mini", "1·1·1·1·1"),
]


def _setup_font():
    for name in ("DejaVu Sans",):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.family"] = name
            break
        except Exception:
            pass
    plt.rcParams["axes.unicode_minus"] = False


def by_key(groups):
    return {(g["bench"], g["cli"], g["model"], g["bits"]): g for g in groups}


READ_ONCE = {"gov_report", "narrativeqa"}  # one big document, seen once (vs agent loop)


def _rows(K):
    """Return two shape-groups, each a list of (label, tok_saved, cost_saved, is_real),
    sorted by cost saved descending. Grouping by task shape lets the chart show that BOTH
    shapes win, not just the easy read-once ones."""
    read_once, agent_loop = [], []
    for key in CELLS:
        g = K.get(key)
        if not g:
            continue
        tok = input_delta(g)
        cost, basis = cost_delta(g)
        if tok is None or cost is None:
            continue
        label = f"{SHORT_MODEL.get(g['model'], g['model'])}  ·  {BENCH_LABEL.get(g['bench'], g['bench'])}"
        row = (label, -tok, -cost, basis == "real")
        (read_once if g["bench"] in READ_ONCE else agent_loop).append(row)
    read_once.sort(key=lambda r: r[2], reverse=True)
    agent_loop.sort(key=lambda r: r[2], reverse=True)
    return [
        ("Read once  ·  one document, seen once", read_once),
        ("Agent loop  ·  big context re-sent every turn", agent_loop),
    ]


BASE_C = "#e2e6ea"  # faded track = the no-imaging baseline (100%)
HEADER_SLOT = 0.95  # vertical space reserved for a group header
GROUP_GAP = 0.7     # extra gap between the two groups


def _layout(groups):
    """Assign y positions top-to-bottom: a header slot then its rows, per group."""
    placements, headers, cur = [], [], 0.0
    for gi, (title, grp) in enumerate(groups):
        if gi > 0:
            cur += GROUP_GAP
        headers.append((title, cur))
        cur += HEADER_SLOT
        for r in grp:
            placements.append((r, cur))
            cur += 1.0
    return placements, headers, cur


def _panel(ax, placements, headers, kind):
    """One before/after panel. Faded track to 100 = imaging OFF; solid bar = what remains
    with imaging ON (shorter is less). The empty slot is the cut, labelled with the % saved."""
    solid = TOKEN_C if kind == "tokens" else COST_C
    txt_c = "#334155" if kind == "tokens" else "#166534"
    for (label, tok, cost, is_real), y in placements:
        saved = tok if kind == "tokens" else cost
        remaining = 100 - saved
        hatch = "///" if (kind == "cost" and is_real) else None
        ax.barh(y, 100, height=0.62, color=BASE_C, zorder=1)
        ax.barh(y, remaining, height=0.62, color=solid, zorder=2,
                edgecolor="white", linewidth=1.1 if hatch else 0, hatch=hatch)
        ax.text((remaining + 100) / 2, y, f"-{saved:.0f}%", ha="center", va="center",
                fontsize=10.5, fontweight="bold", color=txt_c, zorder=4)

    # group headers, in the left gutter (aligned with the row labels)
    for title, y in headers:
        ax.text(-0.01, y, title, transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=10, fontweight="bold", color="#111827", zorder=5)

    ax.axvline(100, color="#9aa3af", lw=1.1, ls=(0, (4, 3)), zorder=3)
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 50, 100])
    ax.tick_params(axis="x", labelsize=9, colors=MUTE)
    ax.tick_params(axis="y", length=0)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.set_title("Input tokens" if kind == "tokens" else "Cost (dollars)",
                 fontsize=13, fontweight="bold", color=solid, pad=10)


def _draw(groups):
    placements, headers, total = _layout(groups)
    n = len(placements)
    fig, (axL, axR) = plt.subplots(1, 2, sharey=True, figsize=(13.2, 0.52 * (total) + 3.1))
    # headers only in the left gutter (shared rows), so pass [] to the right panel
    _panel(axL, placements, headers, "tokens")
    _panel(axR, placements, [], "cost")
    for ax in (axL, axR):
        ax.set_ylim(-0.6, total - 0.4)
        ax.invert_yaxis()  # biggest cut on top

    axL.set_yticks([y for _, y in placements])
    axL.set_yticklabels([r[0] for r, _ in placements], fontsize=11, color=INK)

    fig.text(0.012, 0.982, "imgctx shrinks the request, and the bill shrinks with it",
             fontsize=17.5, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.012, 0.945,
             "Each solid bar is what you pay AFTER imaging, against the faded baseline = the "
             "same task with imaging OFF (100%).",
             fontsize=10.5, color=MUTE, ha="left", va="top")
    fig.text(0.012, 0.917,
             "Shorter is less; the empty slot is the saving. Both read-once and agent-loop "
             "tasks win.",
             fontsize=10.5, color=MUTE, ha="left", va="top")

    handles = [
        Patch(facecolor=BASE_C, label="imaging OFF (baseline, 100%)"),
        Patch(facecolor="#4b5563", label="imaging ON (what remains)"),
        Patch(facecolor="white", edgecolor=INK, hatch="///",
              label="hatched cost = real provider bill (others: list-price sim)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9.5,
               frameon=False, bbox_to_anchor=(0.5, 0.04))
    fig.text(0.5, 0.01,
             "Source: bench/FINAL_REPORT.md. Each row is one agent x model x task at its "
             "task-matched region config (n=1-14 items). Claude Code cost is the real bill; "
             "others simulated from published list prices.",
             fontsize=8.3, color=MUTE, ha="center", va="bottom")
    fig.subplots_adjust(left=0.30, right=0.985, top=0.80, bottom=0.14, wspace=0.08)
    fig.savefig(OUT / "chart_savings.png", dpi=150)
    plt.close(fig)


def main():
    _setup_font()
    OUT.mkdir(parents=True, exist_ok=True)
    # drop the superseded two-chart pair so assets/ holds only the current combined chart
    for old in ("chart_tokens_saved.png", "chart_cost_saved.png"):
        p = OUT / old
        if p.exists():
            p.unlink()
    groups, _, _ = prepare_groups()
    _draw(_rows(by_key(groups)))
    print(f"wrote chart_savings.png to {OUT}/")


if __name__ == "__main__":
    main()
