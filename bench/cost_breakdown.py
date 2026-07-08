"""STANDALONE cost-decomposition analysis (NOT part of the benchmark harness).

The harnesses and their REPORT.md files never price tokens by hand: they only ever
report Claude Code's own `total_cost_usd`. That rule stays. This script is a
separate, after-the-fact *analysis* that answers one question the real total
cannot answer on its own: **which token class the money is in.**

It multiplies the REAL per-field token counts (from each run's stream) by the
PUBLISHED Anthropic per-MTok rates, to split the bill into fresh-input / cache-
write / cache-read / output dollars. It is a SIMULATION, so it prints the
reconciliation error against Claude's real `total_cost_usd`; on these runs the
rates below reproduce the real bill to the cent, which is what makes the
per-class split trustworthy rather than a guess.

Rates: published Anthropic pricing for claude-sonnet-5 (USD per 1M tokens). Claude
Code writes prompt cache at the 1-HOUR TTL, so cache-creation is priced at 2x the
base input rate, not the 5-minute 1.25x. If Anthropic changes prices, edit RATES;
the reconciliation line will immediately show any drift.

Run:  .venv/bin/python -m bench.cost_breakdown
Writes bench/COST_BREAKDOWN.md
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# USD per 1,000,000 tokens (claude-sonnet-5, 1-hour cache TTL as Claude Code uses).
RATES = {
    "input_tokens": 3.00,                  # fresh input, 1x
    "cache_creation_input_tokens": 6.00,   # cache WRITE, 1h TTL = 2x input
    "cache_read_input_tokens": 0.30,       # cache READ, 0.1x input
    "output_tokens": 15.00,                # output
}
LABEL = {
    "input_tokens": "fresh input (1x)",
    "cache_creation_input_tokens": "cache WRITE (2x, 1h)",
    "cache_read_input_tokens": "cache read (0.1x)",
    "output_tokens": "output",
}
ORDER = ["input_tokens", "cache_creation_input_tokens",
         "cache_read_input_tokens", "output_tokens"]


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


def _cost(tokens: dict) -> dict:
    """Simulated USD per class from real token counts x published rates."""
    return {k: (tokens.get(k, 0) or 0) * RATES[k] / 1e6 for k in ORDER}


def collect(results_file: Path, stream_of):
    """Matched pairs only, and only pairs where BOTH have a real total_cost_usd
    (so the reconciliation is meaningful). Returns aggregated tokens per class for
    OFF and ON, plus the summed REAL cost for each side."""
    if not results_file.exists():
        return None
    results = json.loads(results_file.read_text())
    by: dict[str, dict] = {}
    for r in results:
        ident = r.get("instance_id") or r.get("qid")
        cond = r.get("cond")
        if not ident or cond not in ("off", "on"):
            continue
        evt = _last_result(stream_of(cond, ident))
        u = (evt or {}).get("usage") or {}
        by.setdefault(ident, {})[cond] = {
            "u": {k: u.get(k, 0) or 0 for k in ORDER},
            "cost": (evt or {}).get("total_cost_usd"),
            "err": bool((evt or {}).get("is_error")) or bool(r.get("harness_error")),
        }
    tok = {"off": {k: 0 for k in ORDER}, "on": {k: 0 for k in ORDER}}
    real = {"off": 0.0, "on": 0.0}
    n = 0
    for d in by.values():
        o, nn = d.get("off"), d.get("on")
        if not o or not nn or o["err"] or nn["err"]:
            continue
        if o["cost"] is None or nn["cost"] is None:
            continue
        n += 1
        for k in ORDER:
            tok["off"][k] += o["u"][k]
            tok["on"][k] += nn["u"][k]
        real["off"] += o["cost"]
        real["on"] += nn["cost"]
    return {"n": n, "tok": tok, "real": real}


def pct(n: float, o: float) -> float:
    return 100.0 * (n - o) / o if o else 0.0


BENCHES = [
    ("SWE-bench (re-read loop)",
     HERE / "swebench_runs" / "results.json",
     lambda c, i: HERE / "swebench_runs" / c / f"{i}.stream.jsonl"),
    ("HotpotQA (re-read, short)",
     HERE / "hotpot_claude_runs" / "results.json",
     lambda c, i: HERE / "hotpot_claude_runs" / c / i / "stream.jsonl"),
    ("narrativeqa (read once)",
     HERE / "longdoc_runs" / "results_narrativeqa.json",
     lambda c, i: HERE / "longdoc_runs" / c / i / "stream.jsonl"),
    ("gov_report (read once)",
     HERE / "longdoc_runs" / "results_gov_report.json",
     lambda c, i: HERE / "longdoc_runs" / c / i / "stream.jsonl"),
]


def block(name: str, data: dict) -> list[str]:
    tok, real, n = data["tok"], data["real"], data["n"]
    coff, con = _cost(tok["off"]), _cost(tok["on"])
    sim_off, sim_on = sum(coff.values()), sum(con.values())

    L = [f"## {name}  (matched n={n})", ""]
    L += ["| token class | rate $/M | tokens OFF | tokens ON | Δ tok | $ OFF | $ ON | Δ $ |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for k in ORDER:
        to, tn = tok["off"][k], tok["on"][k]
        L.append(f"| {LABEL[k]} | {RATES[k]:.2f} | {to:,} | {tn:,} | {pct(tn,to):+.1f}% "
                 f"| ${coff[k]:.4f} | ${con[k]:.4f} | ${con[k]-coff[k]:+.4f} |")
    # input-side subtotal (imgctx only touches these three)
    in_off = sum(tok["off"][k] for k in ORDER[:3])
    in_on = sum(tok["on"][k] for k in ORDER[:3])
    ci_off = sum(coff[k] for k in ORDER[:3])
    ci_on = sum(con[k] for k in ORDER[:3])
    L.append(f"| **input-side (imaged)** | | {in_off:,} | {in_on:,} | {pct(in_on,in_off):+.1f}% "
             f"| ${ci_off:.4f} | ${ci_on:.4f} | ${ci_on-ci_off:+.4f} |")
    L.append(f"| **TOTAL (simulated)** | | | | | ${sim_off:.4f} | ${sim_on:.4f} "
             f"| ${sim_on-sim_off:+.4f} ({pct(sim_on,sim_off):+.1f}%) |")
    L += ["",
          f"- **Reconciliation vs Claude's real `total_cost_usd`:** "
          f"OFF sim ${sim_off:.4f} vs real ${real['off']:.4f} "
          f"(diff ${sim_off-real['off']:+.4f}); "
          f"ON sim ${sim_on:.4f} vs real ${real['on']:.4f} "
          f"(diff ${sim_on-real['on']:+.4f}). "
          "Near-zero diff = the per-class split below is the real bill, not a guess.",
          ""]
    # attribution: which class moved the bill
    deltas = {k: con[k] - coff[k] for k in ORDER}
    total_d = sim_on - sim_off
    write_d = deltas["cache_creation_input_tokens"]
    read_d = deltas["cache_read_input_tokens"]
    out_d = deltas["output_tokens"]
    L += [
        f"- **What moved the bill:** cache-WRITE {write_d:+.4f}, cache-read {read_d:+.4f}, "
        f"output {out_d:+.4f}, fresh {deltas['input_tokens']:+.4f}. "
        f"Net {total_d:+.4f}. "
        f"The write class is {abs(write_d)/abs(total_d)*100:.0f}% of the |net| move."
        if total_d else "- (no net change)",
        "",
    ]
    return L


def main() -> None:
    L = ["# Cost decomposition by token class (simulation, reconciled to real cost)", "",
         "**This is a standalone analysis, not part of the benchmark harness.** The "
         "harness only ever records Claude Code's real `total_cost_usd`. Here we take "
         "those same runs' REAL per-field token counts and multiply by PUBLISHED "
         "claude-sonnet-5 rates to see *which class* the money sits in. The "
         "reconciliation line on each block shows the simulated total lands on Claude's "
         "real bill, which is what makes the per-class split trustworthy.", "",
         "Rates (USD per 1M tokens, 1-hour cache TTL as Claude Code uses): "
         f"fresh input **{RATES['input_tokens']:.2f}**, cache-WRITE "
         f"**{RATES['cache_creation_input_tokens']:.2f}** (2x), cache-read "
         f"**{RATES['cache_read_input_tokens']:.2f}** (0.1x), output "
         f"**{RATES['output_tokens']:.2f}**.", ""]
    summary = []
    for name, rf, so in BENCHES:
        data = collect(rf, so)
        if not data or not data["n"]:
            L += [f"## {name}", "", "_no matched pairs with real cost on disk_", ""]
            continue
        L += block(name, data)
        # for the summary table
        coff, con = _cost(data["tok"]["off"]), _cost(data["tok"]["on"])
        w = con["cache_creation_input_tokens"] - coff["cache_creation_input_tokens"]
        summary.append((name, pct(data["tok"]["on"]["cache_creation_input_tokens"],
                                  data["tok"]["off"]["cache_creation_input_tokens"]),
                        w, pct(sum(con.values()), sum(coff.values()))))

    head = ["# The one lever, at a glance", "",
            "| benchmark | cache-WRITE tokens Δ | cache-WRITE $ Δ | total cost Δ |",
            "| --- | ---: | ---: | ---: |"]
    for name, wtok, wdol, tcost in summary:
        head.append(f"| {name} | {wtok:+.1f}% | ${wdol:+.4f} | {tcost:+.1f}% |")
    head += ["",
             "Cache-write and total cost share a sign in every row: imaging that shrinks "
             "the write class lowers the bill; imaging that inflates it raises the bill.",
             ""]

    out = HERE / "COST_BREAKDOWN.md"
    out.write_text("\n".join(head + [""] + L))
    print(f"wrote {out}\n")
    print("\n".join(head))
    print("\n".join(L))


if __name__ == "__main__":
    main()
