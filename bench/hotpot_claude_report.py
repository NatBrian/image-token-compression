"""Turn bench/hotpot_claude_runs into a Markdown report, REAL numbers only.

Every figure is real provider data:
  - dollars  = Claude Code's own `total_cost_usd` (read from each run's stream.jsonl),
  - tokens   = Claude's per-field usage (input/cache_creation/cache_read/output),
  - EM/F1/contains = HotpotQA scoring on the model's actual answer.
NO hand-rolled price formula is used anywhere. The only arithmetic applied is
summation and percent-change over those real values (this is labeled where shown).

Matched pairs only: a question counts toward the dollar/token aggregates when BOTH
OFF and ON produced a result event with a real total_cost_usd.

Run:  .venv/bin/python -m bench.hotpot_claude_report
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "hotpot_claude_runs"


def _result_evt(stream: Path):
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


def _real_cost(evt) -> float | None:
    """Claude's own billed dollars. None if absent, never fabricated."""
    if evt and isinstance(evt.get("total_cost_usd"), (int, float)):
        return float(evt["total_cost_usd"])
    return None


def _in_side(u: dict) -> int:
    return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0))


def pct(on: float, off: float) -> float:
    return 100.0 * (on - off) / off if off else 0.0


def load_rows() -> dict[str, dict]:
    """qid -> {off: row, on: row}. Each row carries scoring (from results.json) plus
    the REAL cost + usage read from that question's stream.jsonl."""
    results = json.loads((RUNS / "results.json").read_text())
    by_q: dict[str, dict] = {}
    for r in results:
        qid, cond = r.get("qid"), r.get("cond")
        if not qid or cond not in ("off", "on"):
            continue
        evt = _result_evt(RUNS / cond / qid / "stream.jsonl")
        u = (evt or {}).get("usage") or {}
        by_q.setdefault(qid, {})[cond] = {
            "em": r.get("em"), "f1": r.get("f1"), "contains": r.get("contains"),
            "pred": r.get("pred"), "gold": r.get("gold"),
            "cost": _real_cost(evt),                # real total_cost_usd or None
            "in": _in_side(u), "out": u.get("output_tokens", 0),
            "turns": (evt or {}).get("num_turns"),
        }
    return by_q


def main() -> None:
    by_q = load_rows()
    pairs = [(q, d["off"], d["on"]) for q, d in sorted(by_q.items())
             if "off" in d and "on" in d]

    # Model label straight from a stream (not assumed).
    model = "?"
    for q, _, _ in pairs:
        evt = _result_evt(RUNS / "on" / q / "stream.jsonl") or {}
        m = (evt.get("modelUsage") or {})
        if m:
            model = ", ".join(sorted(m.keys()))
            break

    L = ["# HotpotQA: imgctx A/B on Claude Code, real cost", ""]
    L += [
        "Claude Code CLI (`claude -p`) answering HotpotQA (distractor) multihop "
        "questions, each run twice through an identical proxy: compression OFF "
        "(passthrough) and ON (imgctx). Each question's 10 context paragraphs are "
        "written to a `documents.md`; the agent reads it and returns one `FINAL ANSWER:` "
        "line.",
        "",
        f"Model(s) seen in streams: `{model}`.",
        "",
        "**All dollars are Claude Code's own `total_cost_usd`** (read from each run's "
        "stream). Tokens are Claude's real per-field usage. No price formula is used; "
        "the only math is summation and percent-change over these real values.",
        "",
    ]

    # dollar/token aggregates over pairs where BOTH have a real cost
    dpairs = [(o, n) for _, o, n in pairs if o["cost"] is not None and n["cost"] is not None]
    if dpairs:
        coff = sum(o["cost"] for o, _ in dpairs)
        con = sum(n["cost"] for _, n in dpairs)
        toff = sum(o["in"] for o, _ in dpairs)
        ton = sum(n["in"] for _, n in dpairs)
        emo = sum((o["em"] or 0) for o, _ in dpairs); emn = sum((n["em"] or 0) for _, n in dpairs)
        cto = sum((o["contains"] or 0) for o, _ in dpairs); ctn = sum((n["contains"] or 0) for _, n in dpairs)
        L += [
            f"## Headline, matched n={len(dpairs)} (real cost)", "",
            "| metric | OFF | ON | change |",
            "| --- | ---: | ---: | ---: |",
            f"| input tokens (real) | {toff:,} | {ton:,} | **{pct(ton,toff):+.1f}%** |",
            f"| cost, real total_cost_usd | ${coff:.4f} | ${con:.4f} | **{pct(con,coff):+.1f}%** |",
            f"| exact match | {emo}/{len(dpairs)} | {emn}/{len(dpairs)} | |",
            f"| contains gold | {cto}/{len(dpairs)} | {ctn}/{len(dpairs)} | |",
            "",
        ]
    else:
        L += ["_No matched pair has a real total_cost_usd on disk, cannot report cost._", ""]

    # per-question detail
    L += ["## Per-question (real)", "",
          "| qid | in OFF | in ON | Δ tok | $ OFF | $ ON | Δ $ | EM O/N | turns O/N |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | :--: | :--: |"]
    for q, o, n in pairs:
        du = f"{pct(n['cost'], o['cost']):+.0f}%" if (o["cost"] and n["cost"]) else "n/a"
        oc = f"${o['cost']:.4f}" if o["cost"] is not None else "n/a"
        nc = f"${n['cost']:.4f}" if n["cost"] is not None else "n/a"
        L.append(
            f"| {q} | {o['in']:,} | {n['in']:,} | {pct(n['in'], o['in']):+.1f}% | "
            f"{oc} | {nc} | {du} | {o['em']}/{n['em']} | {o['turns']}/{n['turns']} |")
    L.append("")

    out = RUNS / "REPORT.md"
    out.write_text("\n".join(L))
    print(f"wrote {out}")
    print("\n".join(L[:16]))


if __name__ == "__main__":
    main()
