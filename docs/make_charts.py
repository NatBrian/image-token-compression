"""Generate README charts from the HotpotQA experiment results.

Reads bench/hotpot_runs/results.json (history-collapse run) and
results_v2_tools.json (no-history run), writes PNGs into docs/assets/.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "bench" / "hotpot_runs"
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

OFF_C = "#9aa0a6"   # muted gray
ON_C = "#1f9e8a"    # teal
BAD_C = "#d1495b"   # red
GOOD_C = "#1f9e8a"  # teal

plt.rcParams.update({
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def load(name):
    return json.loads((RUNS / name).read_text())


def by_cond(rows):
    off = {r["qid"]: r for r in rows if r["condition"] == "off"}
    on = {r["qid"]: r for r in rows if r["condition"] == "on"}
    return off, on


def chart_per_question(rows):
    off, on = by_cond(rows)
    qids = sorted(set(off) & set(on))
    off_t = [off[q]["prompt_tokens"] / 1000 for q in qids]
    on_t = [on[q]["prompt_tokens"] / 1000 for q in qids]
    x = range(len(qids))
    w = 0.4
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar([i - w / 2 for i in x], off_t, w, label="without imgctx", color=OFF_C)
    ax.bar([i + w / 2 for i in x], on_t, w, label="with imgctx", color=ON_C)
    ax.set_xticks(list(x))
    ax.set_xticklabels(qids, rotation=0)
    ax.set_ylabel("prompt tokens per question (thousands)")
    ax.set_title("Input tokens per multihop question (OpenCode + mimo-v2.5)", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper right")
    med_off = st.median(off[q]["prompt_tokens"] for q in qids)
    med_on = st.median(on[q]["prompt_tokens"] for q in qids)
    cut = 100 * (med_off - med_on) / med_off
    ax.annotate(f"median cut: -{cut:.0f}%", xy=(0.02, 0.9), xycoords="axes fraction",
                fontsize=12, fontweight="bold", color=ON_C)
    fig.tight_layout()
    fig.savefig(OUT / "tokens_per_question.png", dpi=140)
    plt.close(fig)
    return cut, med_off, med_on


def chart_cost(med_saved_tokens):
    # $ saved per 1,000 agentic questions at representative input prices ($/1M tokens).
    prices = [0.50, 1.25, 3.00, 5.00, 10.00]
    labels = [f"${p:g}/1M" for p in prices]
    saved_per_1k = [med_saved_tokens * 1000 * p / 1_000_000 for p in prices]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(labels, saved_per_1k, color=ON_C, width=0.6)
    ax.set_ylabel("$ saved per 1,000 questions")
    ax.set_xlabel("input-token price ($ / 1M tokens)")
    ax.set_title(f"Cost saved on input tokens (median {med_saved_tokens:,.0f} tokens/question cut)",
                 loc="left", fontweight="bold")
    for b, v in zip(bars, saved_per_1k):
        ax.annotate(f"${v:,.0f}", xy=(b.get_x() + b.get_width() / 2, v),
                    xytext=(0, 6), textcoords="offset points", ha="center", fontweight="bold")
    ax.margins(y=0.18)
    fig.tight_layout()
    fig.savefig(OUT / "cost_savings.png", dpi=140)
    plt.close(fig)
    return dict(zip(labels, saved_per_1k))


if __name__ == "__main__":
    rows = load("results.json")
    cut, med_off, med_on = chart_per_question(rows)
    saved = chart_cost(med_off - med_on)
    print(f"per-question median: {med_off:,.0f} -> {med_on:,.0f}  (-{cut:.0f}%)")
    print(f"cost saved/1k questions: {saved}")
    print(f"charts -> {OUT}")
