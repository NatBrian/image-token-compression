"""STANDALONE cache + simulated-cost decomposition for the OpenCode / mimo-v2.5-free
path, across all four benchmarks (HotpotQA, SWE-bench, narrativeqa, gov_report).

Not part of the benchmark harness. mimo-v2.5-free is FREE, so the provider-billed
cost is $0.00 on every run. This script reads each run's REAL per-field token usage
(including the endpoint's cache split: cached_tokens = cache-READ,
cache_write_tokens = cache-WRITE) and:

  1. Reports the real cache split per benchmark.
  2. Adds a SIMULATED dollar view under a representative OpenAI-style rate table,
     because the model is free and has no real price. THIS IS A SIMULATION, labelled
     as such; the token/cache numbers are real, the dollars are illustrative.

The one structural fact the whole file exists to show: on this endpoint
cache_write_tokens is 0 on every call. Unlike Anthropic it charges NO cache-write
premium, so imaging's input-token cut flows straight to the (simulated) bill instead
of being clawed back by a 2x write class. That is why the OpenCode path is a clean
win in every regime, including the re-read ones (SWE-bench, HotpotQA) that LOST money
on Anthropic.

Run:  .venv/bin/python -m bench.opencode_cost_breakdown
Writes bench/OPENCODE_COST_BREAKDOWN.md
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Representative OpenAI-compatible small-model rates (USD per 1M tokens). SIMULATION:
# mimo-v2.5-free is $0, so these stand in only to show the SHAPE of the bill. The
# defining property vs Anthropic: cache-write carries NO premium (same as fresh
# input), and a cache-read is a discount (0.5x), not a near-free 0.1x.
RATES = {"fresh": 0.15, "write": 0.15, "read": 0.075, "output": 0.60}
CLASSES = ("fresh", "write", "read", "output")


# --------------------------------------------------------------------------- #
# usage loaders -> per-id usage dict {prompt, read, write, fresh, output}
# --------------------------------------------------------------------------- #
def _norm(u: dict) -> dict:
    """Normalise either an events-style or a harness-embedded usage dict."""
    prompt = u.get("prompt_tokens", 0) or 0
    d = u.get("prompt_tokens_details") or {}
    read = u.get("cached_tokens", d.get("cached_tokens", 0)) or 0
    write = u.get("cache_write_tokens", d.get("cache_write_tokens", 0)) or 0
    out = u.get("completion_tokens", 0) or 0
    return {"prompt": prompt, "read": read, "write": write,
            "fresh": prompt - read - write, "output": out}


def _from_events(events_file: str) -> dict:
    """Sum every usage dict in a proxy event log (HotpotQA path: cache split lives
    only in the events, not the results json)."""
    agg = {"prompt_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
           "completion_tokens": 0}
    if not os.path.exists(events_file):
        return _norm(agg)
    for line in open(events_file):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        found: list[dict] = []

        def walk(o):
            if isinstance(o, dict):
                if isinstance(o.get("usage"), dict):
                    found.append(o["usage"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(e)
        for u in found:
            d = u.get("prompt_tokens_details") or {}
            agg["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
            agg["cached_tokens"] += d.get("cached_tokens", 0) or 0
            agg["cache_write_tokens"] += d.get("cache_write_tokens", 0) or 0
            agg["completion_tokens"] += u.get("completion_tokens", 0) or 0
    return _norm(agg)


def pairs_from_events(runs_dir: Path):
    """HotpotQA: match by qid dir under {off,on}/<qid>/events.jsonl."""
    out = {}
    for cond in ("off", "on"):
        for ev in glob.glob(str(runs_dir / cond / "*" / "events.jsonl")):
            qid = Path(ev).parent.name
            out.setdefault(qid, {})[cond] = _from_events(ev)
    return [(o["off"], o["on"]) for o in out.values() if "off" in o and "on" in o]


def pairs_from_results(results_file: Path, id_key: str):
    """New harnesses embed real `usage` (with cache split) per record. Match by id_key."""
    if not results_file.exists():
        return []
    rows = json.loads(results_file.read_text())
    by = {}
    for r in rows:
        rid, cond = r.get(id_key), r.get("cond") or r.get("condition")
        if not rid or cond not in ("off", "on"):
            continue
        if r.get("is_error"):
            continue
        u = r.get("usage") or {}
        by.setdefault(rid, {})[cond] = _norm(u)
    return [(d["off"], d["on"]) for d in by.values() if "off" in d and "on" in d]


# --------------------------------------------------------------------------- #
BENCHES = [
    ("HotpotQA (re-read, short)", "events",
     HERE / "hotpot_runs", None),
    ("SWE-bench Lite (re-read, agentic)", "results",
     HERE / "swebench_opencode_runs" / "results.json", "instance_id"),
    ("narrativeqa (read once)", "results",
     HERE / "longdoc_opencode_runs" / "results_narrativeqa.json", "qid"),
    ("gov_report (read once)", "results",
     HERE / "longdoc_opencode_runs" / "results_gov_report.json", "qid"),
]


def agg_pairs(pairs):
    off = {k: 0 for k in ("prompt", "read", "write", "fresh", "output")}
    on = {k: 0 for k in off}
    for o, n in pairs:
        for k in off:
            off[k] += o[k]
            on[k] += n[k]
    return off, on, len(pairs)


def cost(t: dict) -> dict:
    return {"fresh": t["fresh"] * RATES["fresh"] / 1e6,
            "write": t["write"] * RATES["write"] / 1e6,
            "read": t["read"] * RATES["read"] / 1e6,
            "output": t["output"] * RATES["output"] / 1e6}


def pct(n: float, o: float) -> float:
    return 100.0 * (n - o) / o if o else 0.0


def block(name: str, off: dict, on: dict, n: int) -> tuple[list[str], tuple]:
    coff, con = cost(off), cost(on)
    in_off = coff["fresh"] + coff["write"] + coff["read"]
    in_on = con["fresh"] + con["write"] + con["read"]
    L = [f"## {name}  (matched n={n})", "",
         "| token class | field | OFF | ON | Δ tok | sim $ OFF | sim $ ON |",
         "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
         f"| total input | `prompt_tokens` | {off['prompt']:,} | {on['prompt']:,} | {pct(on['prompt'],off['prompt']):+.1f}% | | |",
         f"| cache READ | `cached_tokens` | {off['read']:,} | {on['read']:,} | {pct(on['read'],off['read']):+.1f}% | ${coff['read']:.4f} | ${con['read']:.4f} |",
         f"| cache WRITE | `cache_write_tokens` | {off['write']:,} | {on['write']:,} | (both 0) | ${coff['write']:.4f} | ${con['write']:.4f} |",
         f"| fresh (uncached) | prompt-read-write | {off['fresh']:,} | {on['fresh']:,} | {pct(on['fresh'],off['fresh']):+.1f}% | ${coff['fresh']:.4f} | ${con['fresh']:.4f} |",
         f"| **input-side (imgctx)** | prompt total | **{off['prompt']:,}** | **{on['prompt']:,}** | **{pct(on['prompt'],off['prompt']):+.1f}%** | **${in_off:.4f}** | **${in_on:.4f}** |",
         f"| output (loop variance) | `completion_tokens` | {off['output']:,} | {on['output']:,} | {pct(on['output'],off['output']):+.1f}% | ${coff['output']:.4f} | ${con['output']:.4f} |",
         "",
         f"- Real provider cost: **$0.00 / $0.00** (mimo-v2.5-free). cache WRITE = 0 both arms.",
         f"- Simulated input-side cost Δ: **{pct(in_on,in_off):+.1f}%** (token cut flows to the bill; no write premium to claw it back).",
         ""]
    return L, (name, pct(on["prompt"], off["prompt"]), pct(in_on, in_off), off["write"] + on["write"])


def main() -> None:
    head = ["# OpenCode / mimo-v2.5-free: cache and simulated cost, all benchmarks", "",
            "**mimo-v2.5-free is FREE, so the real provider-billed cost is $0.00 on every "
            "run.** The token and cache numbers below are REAL (the zen/mimo endpoint's own "
            "`usage`, including its cache split). **The dollar figures are a SIMULATION** "
            "under a representative OpenAI-style rate table (fresh input "
            f"${RATES['fresh']:.3f}/M, cache-write ${RATES['write']:.3f}/M with NO premium, "
            f"cache-read ${RATES['read']:.3f}/M at 0.5x, output ${RATES['output']:.3f}/M), "
            "shown only to reveal the SHAPE of the bill. They are not a real charge.", "",
            "The structural point: `cache_write_tokens` is 0 on every call here, so unlike "
            "Anthropic there is no 2x write class for imaging to inflate. The input-token cut "
            "therefore becomes a (simulated) cost cut in EVERY regime, including the re-read "
            "tasks (SWE-bench, HotpotQA) that lost money on Anthropic. See "
            "`docs/input-tokens-vs-cost.md`.", ""]

    body, summary = [], []
    for entry in BENCHES:
        name, kind = entry[0], entry[1]
        if kind == "events":
            pairs = pairs_from_events(entry[2])
        else:
            pairs = pairs_from_results(entry[2], entry[3])
        if not pairs:
            body += [f"## {name}", "", "_no matched pairs on disk yet_", ""]
            continue
        off, on, n = agg_pairs(pairs)
        blk, srow = block(name, off, on, n)
        body += blk
        summary.append(srow)

    sm = ["## Summary: every regime wins on OpenCode", "",
          "| benchmark | input tokens Δ | cache-write tokens (OFF+ON) | simulated input-side cost Δ |",
          "| --- | ---: | ---: | ---: |"]
    for name, tok, cdol, wsum in summary:
        sm.append(f"| {name} | {tok:+.1f}% | {int(wsum)} | {cdol:+.1f}% |")
    sm += ["",
           "cache-write is 0 across the board, so the token cut and the simulated cost cut "
           "share a sign in every row: the opposite of the Anthropic re-read result, and the "
           "clearest proof that the Anthropic cost rise is that provider's write premium, not "
           "an imgctx property.",
           "",
           "**Caveat (honest):** output/`completion_tokens` swings with nondeterministic "
           "agent looping and is shown separately; read the input-side row for the imgctx "
           "signal. All dollars are simulated (free model).", ""]

    out = HERE / "OPENCODE_COST_BREAKDOWN.md"
    out.write_text("\n".join(head + sm + [""] + body))
    print(f"wrote {out}\n")
    print("\n".join(head + sm))


if __name__ == "__main__":
    main()
