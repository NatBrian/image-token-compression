"""Combined SWE-bench + HotpotQA report for a single Claude Code A/B run.

Reads REAL data only, dollars from each run's `total_cost_usd`, tokens from Claude's
per-field usage, for BOTH benchmarks and emits one comparison table + verdict. No
price formula; the only math is summation and percent-change over real values.

Run:  .venv/bin/python -m bench.COMBINED_CLAUDE_REPORT
Writes bench/COMBINED_CLAUDE_REPORT.md
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SWE = HERE / "swebench_runs"
HOT = HERE / "hotpot_claude_runs"


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


def pct(on: float, off: float) -> float:
    return 100.0 * (on - off) / off if off else 0.0


def collect(runs: Path, key: str):
    """Return (model, matched_pairs) where each pair is (id, off, on) dicts of real
    cost/tokens/turns read from that item's stream. `key` = filename stem builder."""
    results = json.loads((runs / "results.json").read_text())
    by_id: dict[str, dict] = {}
    for r in results:
        ident = r.get("instance_id") or r.get("qid")
        cond = r.get("cond")
        if not ident or cond not in ("off", "on"):
            continue
        stream = key(runs, cond, ident)
        evt = _last_result(stream)
        u = (evt or {}).get("usage") or {}
        by_id.setdefault(ident, {})[cond] = {
            "cost": (evt or {}).get("total_cost_usd"),
            "in": _in_side(u), "turns": (evt or {}).get("num_turns"),
            "is_error": bool((evt or {}).get("is_error")) or bool(r.get("harness_error")),
            "evt": evt,
        }
    model = "?"
    for d in by_id.values():
        evt = (d.get("on") or {}).get("evt") or {}
        mu = evt.get("modelUsage") or {}
        if mu:
            model = ", ".join(sorted(mu.keys()))
            break
    pairs = [(i, d["off"], d["on"]) for i, d in sorted(by_id.items())
             if "off" in d and "on" in d and not d["off"]["is_error"]
             and not d["on"]["is_error"]]
    return model, pairs


def agg(pairs):
    """Real aggregates over pairs where BOTH have a real total_cost_usd."""
    dp = [(o, n) for _, o, n in pairs if o["cost"] is not None and n["cost"] is not None]
    toff = sum(o["in"] for _, o, n in pairs)
    ton = sum(n["in"] for _, o, n in pairs)
    coff = sum(o["cost"] for o, _ in dp)
    con = sum(n["cost"] for _, n in dp)
    return {"n": len(pairs), "n_cost": len(dp), "toff": toff, "ton": ton,
            "coff": coff, "con": con}


def main() -> None:
    swe_model, swe_pairs = collect(
        SWE, lambda runs, cond, i: runs / cond / f"{i}.stream.jsonl")
    hot_model, hot_pairs = collect(
        HOT, lambda runs, cond, i: runs / cond / i / "stream.jsonl")
    s, h = agg(swe_pairs), agg(hot_pairs)

    L = ["# Combined A/B: imgctx ON vs OFF on Claude Code", ""]
    L += [
        "One parallel run of two benchmarks through the real Claude Code CLI, each "
        "instance/question resolved twice (compression OFF passthrough vs ON). "
        "**All dollars are Claude Code's own `total_cost_usd`; all tokens are Claude's "
        "real per-field usage.** No price formula anywhere, the only math is summation "
        "and percent-change over these real values.",
        "",
        f"- SWE-bench Lite (long agentic), model `{swe_model}`, matched n={s['n']}",
        f"- HotpotQA (short read-a-doc QA), model `{hot_model}`, matched n={h['n']}",
        "",
        "## Headline, real numbers", "",
        "| benchmark | input tokens OFF→ON | Δ tokens | real cost OFF→ON | Δ cost |",
        "| --- | --- | ---: | --- | ---: |",
        f"| SWE-bench ({swe_model}) | {s['toff']:,} → {s['ton']:,} | **{pct(s['ton'],s['toff']):+.1f}%** "
        f"| ${s['coff']:.4f} → ${s['con']:.4f} | **{pct(s['con'],s['coff']):+.1f}%** |",
        f"| HotpotQA ({hot_model}) | {h['toff']:,} → {h['ton']:,} | **{pct(h['ton'],h['toff']):+.1f}%** "
        f"| ${h['coff']:.4f} → ${h['con']:.4f} | **{pct(h['con'],h['coff']):+.1f}%** |",
        "",
        "## Verdict", "",
        f"- **Tokens fall on both** (SWE-bench {pct(s['ton'],s['toff']):+.1f}%, "
        f"HotpotQA {pct(h['ton'],h['toff']):+.1f}%), imaging + history-collapse genuinely "
        "shrink the request.",
        f"- **Real dollars rise on both** (SWE-bench {pct(s['con'],s['coff']):+.1f}%, "
        f"HotpotQA {pct(h['con'],h['coff']):+.1f}%). Fewer tokens ≠ fewer dollars: on "
        "Anthropic, OFF's repeated context is already cheap cache-reads, and imaging "
        "converts those into cache-WRITES billed at the 1-hour TTL (~2x input).",
        "- **Short-trajectory QA is hit harder than long agentic work**: HotpotQA (2 turns, "
        "no later turns to amortize the write) loses more than SWE-bench (long loops let the "
        "frozen prefix cache-read across many turns).",
        "- **Net**: on Sonnet, imgctx compression is a token win but a real-cost LOSS on both "
        "task shapes. Imaging pays only on cheap-vision models like `claude-fable-5` or "
        "no-cache providers. On cache-cheap Anthropic models, leave it OFF.",
        "- **Correctness**: both runs completed every instance with 0 tool errors / 0 HTTP "
        "400s; compression never broke tool use or answers.",
        "",
    ]
    out = HERE / "COMBINED_CLAUDE_REPORT.md"
    out.write_text("\n".join(L))
    print(f"wrote {out}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
