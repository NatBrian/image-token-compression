"""Generate one detailed markdown report over EVERY benchmark run on disk.

Walks a fixed list of run folders, finds every `results*.json`, normalizes the
several usage/cost shapes that accumulated across the project's history, and emits:

  * a global summary table (one line per run: agent/model/bench/N + input & cost deltas)
  * a detailed section per run:
      - per-condition aggregate (OFF vs ON): every token class, BOTH real and
        simulated cost, deltas, avg calls/turns, images, score, errors
      - a per-item table so nothing is hidden

Cost policy (each run shows BOTH so you can choose later):
  * REAL   -- taken verbatim when present: Anthropic rows carry Claude Code's
             `cost_usd` (real_provider); some endpoints report `usage.cost_usd`
             (real_endpoint). Never recomputed.
  * SIMULATED -- always computed from tokens x a per-model list rate table, clearly
             labelled, so free/subscription runs (mimo, codex, gemini) have a dollar
             figure and paid runs can be cross-checked.

Nothing is rerun; every number is regenerated from the captured results files.

Run:  .venv/bin/python -m bench.generate_full_report [--out bench/FULL_REPORT.md]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Folders to scan (relative to bench/). Every results*.json under these is included.
RUN_DIRS = [
    "campaign_20260710_180022",
    "campaign_dryrun_20260710_152928",
    "claude_nqa_hist0_20260710_182803",
    "mimo_refix_20260710_160813",
    "hotpot_claude_runs",
    "hotpot_opencode_runs",
    "hotpot_opencode_runs_gemini_31_flash_lite_v2",
    "hotpot_runs",
    "hotpot_verify_runs",
    "longdoc_claude_runs",
    "longdoc_opencode_runs",
    "longdoc_opencode_runs_gemini_31_flash_lite",
    "longdoc_opencode_runs_gpt_54_mini",
    "swebench_claude_runs",
    "swebench_opencode_runs",
    "swebench_opencode_runs_gemini_31_flash_lite",
]

# Per-model list rates, USD per 1M tokens: (fresh_input, cache_write, cache_read, output, source)
RATES = {
    "anthropic_sonnet": (3.00, 3.75, 0.30, 15.00, "Anthropic claude-sonnet list"),
    "anthropic_haiku":  (1.00, 1.25, 0.10,  5.00, "Anthropic claude-haiku list"),
    "openai_gpt54mini": (0.75, 0.00, 0.075, 4.50, "OpenAI gpt-5.4-mini list"),
    "openai_gpt4omini": (0.15, 0.00, 0.075, 0.60, "OpenAI gpt-4o-mini list"),
    "mimo":             (0.14, 0.00, 0.003, 0.28, "Xiaomi MiMo-V2.5 first-party list"),
    "gemini_flash_lite":(0.10, 0.00, 0.025, 0.40, "Gemini 3.1 flash-lite approx list"),
}


def classify(path: str, meta: dict | None) -> dict:
    """Infer agent / model / family / rate-key from run_meta (new runs) or the
    folder+file name (older runs). Returns a dict with those + a human label."""
    p = path.lower()
    fam = agent = model = rate = None
    if meta:
        agent = meta.get("agent"); fam = meta.get("family"); model = meta.get("model")
    # family/model by path signal (works for old runs and refines new ones)
    if "gemini" in p:
        fam, model, rate = "google", model or "gemini-3.1-flash-lite", "gemini_flash_lite"
        agent = agent or "opencode"
    elif "codex" in p:
        fam, model, rate = "openai", model or "gpt-5.4-mini", "openai_gpt54mini"
        agent = agent or "codex"
    elif "gpt_54_mini" in p or "gpt54mini" in p:
        fam, model, rate = "openai", model or "gpt-5.4-mini", "openai_gpt54mini"
        agent = agent or "opencode"
    elif "gpt4omini" in p:
        fam, model, rate = "openai", "gpt-4o-mini", "openai_gpt4omini"
        agent = agent or "opencode"
    elif "claude" in p or (fam == "anthropic"):
        fam = "anthropic"
        agent = agent or "claude"
        if "haiku" in p:
            model, rate = "claude-haiku", "anthropic_haiku"
        else:
            model, rate = model or "claude-sonnet", "anthropic_sonnet"
    elif "mimo" in p or fam == "mimo":
        fam, model, rate = "mimo", model or "mimo-v2.5-free", "mimo"
        agent = agent or "opencode"
    else:
        # opencode default path (longdoc_opencode_runs, swebench_opencode_runs, hotpot_runs)
        fam, model, rate = "mimo", model or "mimo-v2.5-free", "mimo"
        agent = agent or "opencode"
    return {"agent": agent, "family": fam, "model": model, "rate_key": rate}


def norm_tokens(row: dict) -> dict:
    """Collapse the 3 usage shapes (+ oldest flat shape) into one token schema."""
    u = row.get("usage") or {}
    if "input_tokens" in u or "cache_creation_input_tokens" in u:      # claude shape
        fresh = u.get("input_tokens", 0) or 0
        cwrite = u.get("cache_creation_input_tokens", 0) or 0
        cread = u.get("cache_read_input_tokens", 0) or 0
        out = u.get("output_tokens", 0) or 0
        calls = row.get("num_turns")
        images = None            # Anthropic usage carries no image count
        compressed = None
    elif u:                                                            # opencode/codex/gemini shape
        fresh = u.get("fresh_tokens")
        if fresh is None:
            fresh = (u.get("prompt_tokens", 0) or 0) - (u.get("cached_tokens", 0) or 0) - (u.get("cache_write_tokens", 0) or 0)
        cread = u.get("cached_tokens", 0) or 0
        cwrite = u.get("cache_write_tokens", 0) or 0
        out = u.get("completion_tokens", 0) or 0
        calls = u.get("calls")
        images = u.get("images", 0) or 0
        compressed = u.get("compressed_calls")
    else:                                                             # oldest flat shape (hotpot_runs)
        fresh = row.get("prompt_tokens", 0) or 0
        cread = cwrite = 0
        out = row.get("completion_tokens", 0) or 0
        calls = row.get("calls")
        images = row.get("images", 0) or 0
        compressed = row.get("compressed_calls")
    return {"fresh": max(fresh, 0), "cache_read": cread, "cache_write": cwrite,
            "output": out, "input_total": max(fresh, 0) + cread + cwrite,
            "calls": calls, "images": images, "compressed": compressed}


def real_cost(row: dict, fam: str) -> tuple[float | None, str | None]:
    """Real cost only when the source actually reported one."""
    u = row.get("usage") or {}
    if fam == "anthropic" and row.get("cost_usd") is not None:
        return float(row["cost_usd"]), "real_provider (Claude Code total_cost_usd)"
    if u.get("has_cost") and u.get("cost_usd") is not None:
        return float(u["cost_usd"]), "real_endpoint (usage.cost_usd)"
    if row.get("cost_basis") == "real_provider" and row.get("cost_usd") is not None:
        return float(row["cost_usd"]), "real_provider"
    return None, None


def sim_cost(t: dict, rate_key: str | None) -> float | None:
    if not rate_key or rate_key not in RATES:
        return None
    rin, rcw, rcr, rout, _ = RATES[rate_key]
    return (t["fresh"] * rin + t["cache_write"] * rcw + t["cache_read"] * rcr + t["output"] * rout) / 1e6


def cond_of(row: dict) -> str | None:
    c = row.get("cond") or row.get("condition")
    return c if c in ("off", "on") else None


def bench_of(row: dict, path: str) -> str:
    if row.get("config"):
        return row["config"]
    p = path.lower()
    for b in ("hotpot", "swebench", "narrativeqa", "gov_report"):
        if b in p:
            return b
    return "unknown"


def load_meta(results_path: Path) -> dict | None:
    suffix = results_path.stem[len("results"):]
    for cand in [results_path.parent / f"run_meta{suffix}.json",
                 *sorted(results_path.parent.glob("run_meta*.json"))]:
        if cand.exists():
            try:
                return json.loads(cand.read_text())
            except Exception:
                pass
    return None


def pct(o: float | None, n: float | None) -> str:
    if not o or o == 0 or n is None:
        return "—"
    return f"{100.0 * (n - o) / o:+.1f}%"


def fmt_usd(v):
    # Wrap in backticks: a bare "$" starts a LaTeX math span in many markdown
    # renderers (GitHub etc.), so "$0.83 | $0.47" would merge two table columns.
    # A code span renders the dollar sign literally and keeps the columns intact.
    return f"`${v:.4f}`" if isinstance(v, (int, float)) else "—"


def collect():
    """Return list of run dicts, each = one (results file, benchmark) grouping."""
    runs = []
    for d in RUN_DIRS:
        for f in sorted(glob.glob(f"bench/{d}/**/results*.json", recursive=True)):
            fp = Path(f)
            try:
                data = json.loads(fp.read_text())
            except Exception:
                continue
            if not isinstance(data, list) or not data:
                continue
            meta = load_meta(fp)
            cls = classify(f, meta)
            # a file may hold >1 benchmark/config -> split
            by_bench: dict[str, list] = {}
            for row in data:
                by_bench.setdefault(bench_of(row, f), []).append(row)
            rel = f[len("bench/"):] if f.startswith("bench/") else f  # strip LEADING only
            for bench, rows in by_bench.items():
                runs.append({"path": f, "rel": rel, "meta": meta,
                             "bench": bench, "rows": rows, "mtime": os.path.getmtime(f), **cls})
    return runs


def aggregate(rows, fam, rate_key):
    arms = {}
    for row in rows:
        c = cond_of(row)
        if c is None:
            continue
        a = arms.setdefault(c, {"n": 0, "err": 0, "fresh": 0, "cache_read": 0, "cache_write": 0,
                                "output": 0, "input_total": 0, "images": 0, "calls": [],
                                "real": 0.0, "real_n": 0, "sim": 0.0, "f1": [], "em": [],
                                "contains": [], "patch": [], "dur": []})
        t = norm_tokens(row)
        a["n"] += 1
        if row.get("is_error"):
            a["err"] += 1
        for k in ("fresh", "cache_read", "cache_write", "output", "input_total"):
            a[k] += t[k]
        if t["images"]:
            a["images"] += t["images"]
        if t["calls"] is not None:
            a["calls"].append(t["calls"])
        rc, _ = real_cost(row, fam)
        if rc is not None:
            a["real"] += rc; a["real_n"] += 1
        sc = sim_cost(t, rate_key)
        if sc is not None:
            a["sim"] += sc
        for k in ("f1", "em", "contains"):
            if isinstance(row.get(k), (int, float)):
                a[k].append(row[k])
        if "produced_patch" in row:
            a["patch"].append(bool(row["produced_patch"]))
        if isinstance(row.get("duration_s"), (int, float)):
            a["dur"].append(row["duration_s"])
    return arms


def avg(xs):
    return sum(xs) / len(xs) if xs else None


def render_run(run) -> str:
    fam, rate_key = run["family"], run["rate_key"]
    arms = aggregate(run["rows"], fam, rate_key)
    L = []
    src = RATES.get(rate_key, (0, 0, 0, 0, "n/a"))[4] if rate_key else "n/a"
    L.append(f"### `{run['rel']}` — {run['bench']}")
    L.append(f"agent **{run['agent']}** · model **{run['model']}** · family **{fam}** · "
             f"sim-rate _{src}_")
    if "off" not in arms or "on" not in arms:
        L.append(f"_only arms {list(arms)} present — no delta_\n")
        return "\n".join(L)
    o, n = arms["off"], arms["on"]

    def row(label, key, kfmt=lambda v: f"{v:,}"):
        return f"| {label} | {kfmt(o[key])} | {kfmt(n[key])} | {pct(o[key], n[key])} |"

    L.append("")
    L.append("| metric | OFF | ON | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(row("items", "n"))
    L.append(f"| errors | {o['err']} | {n['err']} | — |")
    L.append(row("input total", "input_total"))
    L.append(row("· fresh", "fresh"))
    L.append(row("· cache-read", "cache_read"))
    L.append(row("· cache-write", "cache_write"))
    L.append(row("output", "output"))
    ac_o, ac_n = avg(o["calls"]), avg(n["calls"])
    L.append(f"| avg calls/turns | {ac_o:.1f} | {ac_n:.1f} | {pct(ac_o, ac_n)} |"
             if ac_o and ac_n else f"| avg calls/turns | {ac_o} | {ac_n} | — |")
    L.append(f"| ON images (sum) | — | {n['images']:,} | — |")
    # cost: real (if any) + simulated (always if rate known)
    ro = o["real"] if o["real_n"] else None
    rn = n["real"] if n["real_n"] else None
    L.append(f"| **cost REAL** | {fmt_usd(ro)} | {fmt_usd(rn)} | {pct(ro, rn)} |")
    so = o["sim"] if rate_key else None
    sn = n["sim"] if rate_key else None
    L.append(f"| **cost SIMULATED** | {fmt_usd(so)} | {fmt_usd(sn)} | {pct(so, sn)} |")
    # score
    if o["patch"] or n["patch"]:
        po = f"{sum(o['patch'])}/{len(o['patch'])}" if o["patch"] else "—"
        pn = f"{sum(n['patch'])}/{len(n['patch'])}" if n["patch"] else "—"
        L.append(f"| patches produced | {po} | {pn} | — |")
    if o["f1"] or n["f1"]:
        f_o, f_n = avg(o["f1"]), avg(n["f1"])
        L.append(f"| F1 (avg) | {f_o:.3f} | {f_n:.3f} | {pct(f_o, f_n)} |" if f_o is not None and f_n is not None
                 else f"| F1 (avg) | {f_o} | {f_n} | — |")
    if o["contains"] or n["contains"]:
        c_o, c_n = avg(o["contains"]), avg(n["contains"])
        L.append(f"| contains (avg) | {c_o:.3f} | {c_n:.3f} | — |")
    du_o, du_n = avg(o["dur"]), avg(n["dur"])
    if du_o and du_n:
        L.append(f"| avg duration s | {du_o:.0f} | {du_n:.0f} | — |")
    L.append("")

    # per-item detail
    L.append("<details><summary>per-item detail</summary>\n")
    L.append("| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |")
    L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|")
    for r in run["rows"]:
        c = cond_of(r)
        if c is None:
            continue
        t = norm_tokens(r)
        rc, _ = real_cost(r, fam)
        sc = sim_cost(t, rate_key)
        idv = r.get("qid") or r.get("instance_id") or "?"
        if "produced_patch" in r:
            score = "patch" if r.get("produced_patch") else "no-patch"
        elif isinstance(r.get("f1"), (int, float)):
            score = f"f1={r['f1']:.2f}"
        else:
            score = "—"
        cl = t["calls"] if t["calls"] is not None else "—"
        im = t["images"] if t["images"] is not None else "—"
        L.append(f"| {str(idv)[:22]} | {c} | {cl} | {t['fresh']:,} | {t['cache_read']:,} | "
                 f"{t['cache_write']:,} | {t['output']:,} | {im} | {fmt_usd(rc)} | {fmt_usd(sc)} | "
                 f"{score} | {'Y' if r.get('is_error') else ''} |")
    L.append("\n</details>\n")
    return "\n".join(L)


def render_summary(runs) -> str:
    L = ["## Summary — every run (delta = ON vs OFF)\n"]
    L.append("| run | agent | model | bench | N | input Δ | real cost Δ | sim cost Δ |")
    L.append("|---|---|---|---|--:|--:|--:|--:|")
    for run in runs:
        arms = aggregate(run["rows"], run["family"], run["rate_key"])
        if "off" not in arms or "on" not in arms:
            continue
        o, n = arms["off"], arms["on"]
        ro = o["real"] if o["real_n"] else None
        rn = n["real"] if n["real_n"] else None
        so = o["sim"] if run["rate_key"] else None
        sn = n["sim"] if run["rate_key"] else None
        short = run["rel"].replace("/results", "/").replace(".json", "")
        L.append(f"| {short} | {run['agent']} | {run['model']} | {run['bench']} | {o['n']}+{n['n']} | "
                 f"{pct(o['input_total'], n['input_total'])} | {pct(ro, rn)} | {pct(so, sn)} |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/FULL_REPORT.md")
    args = ap.parse_args()

    runs = collect()
    # order: by benchmark then agent then path for readability
    runs.sort(key=lambda r: (r["bench"], r["family"], r["rel"]))

    blocks = ["# Full benchmark report — all runs\n",
              f"_Generated from {len(RUN_DIRS)} run folders; {len(runs)} (file × benchmark) runs. "
              "Every number regenerated from captured results — nothing rerun._\n",
              "**Cost columns:** REAL = provider/endpoint-reported (verbatim); "
              "SIMULATED = tokens × per-model list rate (labelled per run). Both shown so the "
              "final report can pick either.\n",
              "### Rate tables used for SIMULATED cost (USD / 1M tokens)\n",
              "| model class | fresh | cache-write | cache-read | output | source |",
              "|---|--:|--:|--:|--:|---|"]
    for k, (ri, cw, cr, ro, src) in RATES.items():
        blocks.append(f"| {k} | {ri} | {cw} | {cr} | {ro} | {src} |")
    blocks.append("")
    blocks.append(render_summary(runs))
    blocks.append("## Detailed runs\n")
    cur = None
    for run in runs:
        if run["bench"] != cur:
            cur = run["bench"]
            blocks.append(f"\n# ▶ Benchmark: {cur}\n")
        blocks.append(render_run(run))

    Path(args.out).write_text("\n".join(blocks))
    print(f"wrote {args.out}  ({len(runs)} runs from {len(RUN_DIRS)} folders)")


if __name__ == "__main__":
    main()
