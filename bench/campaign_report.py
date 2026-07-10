"""Uniform ON/OFF reporter for the benchmark campaign.

Reads one or more `results*.json` files (each an A/B run written by any of the 8
drivers) and prints a single normalized comparison table: input / output /
cache-read / cache-write tokens and cost, ON vs OFF, with % deltas and an explicit
cost_basis (real_provider vs simulated).

The drivers store `usage` in two different shapes:
  * claude (`_sum_usage`):   input_tokens / cache_creation_input_tokens /
                             cache_read_input_tokens / output_tokens
  * codex+opencode (read_usage): fresh_tokens / cache_write_tokens /
                             cached_tokens / completion_tokens
`normalize()` collapses both into one schema so every cell is compared identically.

Cost is taken verbatim from each item's `cost_usd` (real for claude, simulated for
codex/mimo: the driver already applied bench._profiles.cost_for). We never
recompute here; we only sum and delta what the run recorded.

Usage:
  python -m bench.campaign_report bench/hotpot_verify_runs/codex/results.json
  python -m bench.campaign_report 'bench/*_runs*/results*.json'   # glob (quote it)
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def normalize(u: dict) -> dict:
    """Collapse either usage shape into fresh/cache_read/cache_write/output."""
    u = u or {}
    fresh = u.get("fresh_tokens")
    if fresh is None:
        fresh = u.get("input_tokens", 0) or 0
    cread = u.get("cached_tokens", u.get("cache_read_input_tokens", 0)) or 0
    cwrite = u.get("cache_write_tokens", u.get("cache_creation_input_tokens", 0)) or 0
    out = u.get("completion_tokens", u.get("output_tokens", 0)) or 0
    return {
        "fresh": fresh, "cache_read": cread, "cache_write": cwrite, "output": out,
        "input_total": fresh + cread + cwrite,
    }


def _pct(old: float, new: float) -> str:
    if not old:
        return "  n/a"
    return f"{100.0 * (new - old) / old:+5.1f}%"


def summarize(results_path: Path) -> dict | None:
    try:
        data = json.loads(results_path.read_text())
    except Exception as e:
        return {"path": str(results_path), "error": str(e)}
    if not isinstance(data, list) or not data:
        return {"path": str(results_path), "error": "empty/not a list"}

    # optional run_meta sidecar (agent/family/profile). Best-effort.
    # A results file is `results{suffix}.json`; its meta is `run_meta{suffix}.json`.
    # Match on suffix FIRST so that when two configs share a folder (e.g.
    # results_narrativeqa.json + results_gov_report.json) each picks its own meta
    # instead of whichever run_meta*.json globs first. Fall back to any meta.
    suffix = results_path.stem[len("results"):]  # "_narrativeqa" | "_sonnet" | ""
    meta = None
    cands = [results_path.parent / f"run_meta{suffix}.json",
             *sorted(results_path.parent.glob("run_meta*.json"))]
    for cand in cands:
        if not cand.exists():
            continue
        try:
            meta = json.loads(cand.read_text())
            break
        except Exception:
            pass

    arms: dict[str, dict] = {}
    for it in data:
        cond = it.get("cond")
        if cond not in ("off", "on"):
            continue
        a = arms.setdefault(cond, {
            "n": 0, "fresh": 0, "cache_read": 0, "cache_write": 0, "output": 0,
            "input_total": 0, "cost": 0.0, "cost_n": 0, "cost_basis": None,
            "f1": 0.0, "f1_n": 0, "imgs": 0,
        })
        a["n"] += 1
        nu = normalize(it.get("usage"))
        for k in ("fresh", "cache_read", "cache_write", "output", "input_total"):
            a[k] += nu[k]
        c = it.get("cost_usd")
        if c is not None:
            a["cost"] += c
            a["cost_n"] += 1
        if a["cost_basis"] is None and it.get("cost_basis"):
            a["cost_basis"] = it.get("cost_basis")
        if isinstance(it.get("f1"), (int, float)):
            a["f1"] += it["f1"]
            a["f1_n"] += 1
        a["imgs"] += (it.get("usage") or {}).get("images", 0) or 0

    return {"path": str(results_path), "meta": meta, "arms": arms}


def render(summary: dict) -> str:
    if summary.get("error"):
        return f"### {summary['path']}\n_skip: {summary['error']}_\n"
    arms = summary["arms"]
    meta = summary.get("meta") or {}
    agent = meta.get("agent", "?")
    fam = meta.get("family", "?")
    bench = meta.get("benchmark", "?")
    lines = [f"### {Path(summary['path']).parent.name}/{Path(summary['path']).name}"]
    lines.append(f"agent=`{agent}` family=`{fam}` benchmark=`{bench}`")
    if "off" not in arms or "on" not in arms:
        lines.append(f"_arms present: {list(arms)} (need both off+on for a delta)_\n")
        return "\n".join(lines)
    o, n = arms["off"], arms["on"]
    basis = n["cost_basis"] or o["cost_basis"] or "?"
    hdr = "| metric | OFF | ON | Δ |"
    sep = "|---|---:|---:|---:|"
    rows = [hdr, sep]
    for key, label in [("input_total", "input (total)"), ("fresh", "  fresh"),
                       ("cache_read", "  cache-read"), ("cache_write", "  cache-write"),
                       ("output", "output")]:
        rows.append(f"| {label} | {o[key]:,} | {n[key]:,} | {_pct(o[key], n[key])} |")
    # Backtick the $ so markdown renderers with math support don't read "$..$" as a
    # LaTeX span and merge adjacent table columns.
    ocost = f"`${o['cost']:.4f}`" if o["cost_n"] else "n/a"
    ncost = f"`${n['cost']:.4f}`" if n["cost_n"] else "n/a"
    dcost = _pct(o["cost"], n["cost"]) if (o["cost_n"] and n["cost_n"]) else "  n/a"
    rows.append(f"| **cost ({basis})** | {ocost} | {ncost} | {dcost} |")
    of1 = f"{o['f1']/o['f1_n']:.3f}" if o["f1_n"] else "-"
    nf1 = f"{n['f1']/n['f1_n']:.3f}" if n["f1_n"] else "-"
    rows.append(f"| F1 (avg) | {of1} | {nf1} | n/a |")
    rows.append(f"| items / ON images | {o['n']} / n/a | {n['n']} / {n['imgs']} | n/a |")
    lines.append("\n".join(rows))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="results*.json files or globs")
    ap.add_argument("--out", default=None, help="write markdown here instead of stdout")
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        matched = [Path(m) for m in glob.glob(p)]
        files.extend(matched or [Path(p)])
    files = sorted({f for f in files if f.name.startswith("results")})

    blocks = ["# Campaign ON/OFF comparison\n"]
    for f in files:
        s = summarize(f)
        if s:
            blocks.append(render(s))
    text = "\n".join(blocks)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
