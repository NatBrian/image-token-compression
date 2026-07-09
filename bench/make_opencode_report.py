"""Generate a markdown report from bench/hotpot_runs/results.json."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "bench" / "hotpot_runs"


def load() -> list[dict]:
    return json.loads((RUNS / "results.json").read_text())


def by_cond(rows: list[dict]) -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d[r["condition"]].append(r)
    return d


def median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def agg(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {}
    return {
        "n": n,
        "calls": sum(r["calls"] for r in rows),
        "compressed_calls": sum(r["compressed_calls"] for r in rows),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "completion_tokens": sum(r["completion_tokens"] for r in rows),
        "images": sum(r["images"] for r in rows),
        "em": sum(r["em"] for r in rows),
        "contains": sum(r["contains"] for r in rows),
        "f1": sum(r["f1"] for r in rows) / n,
        "wall_s": sum(r["wall_s"] for r in rows),
        "doc_chars": sum(r["doc_chars"] for r in rows),
    }


def pct(off: float, on: float) -> str:
    """Change in token count ON relative to OFF. Negative = fewer tokens (savings)."""
    if not off:
        return "n/a"
    return f"{100*(on-off)/off:+.1f}%"


def main():
    rows = load()
    cond = by_cond(rows)
    off = agg(cond.get("off", []))
    on = agg(cond.get("on", []))

    # Per-question paired view keyed by qid.
    off_by_q = {r["qid"]: r for r in cond.get("off", [])}
    on_by_q = {r["qid"]: r for r in cond.get("on", [])}
    qids = sorted(set(off_by_q) & set(on_by_q))

    regions = defaultdict(int)
    for r in cond.get("on", []):
        for k, v in (r.get("regions") or {}).items():
            regions[k] += v

    L: list[str] = []
    L.append("# imgctx, HotpotQA End-to-End Experiment\n")
    L.append(
        "Multihop QA (HotpotQA distractor, validation split) driven through the "
        "**real OpenCode CLI** (`opencode run`, model `mimo-v2.5-free`). Each "
        "question's 10 context paragraphs are written to `documents.md`; OpenCode "
        "reads the file (tool call) and answers. Every LLM call is routed through "
        "the imgctx proxy and its token usage logged. **OFF** = proxy in "
        "pure-passthrough mode; **ON** = imgctx compression active. Same questions, "
        "same instrument.\n"
    )

    # Matched-trajectory subset: questions where OFF and ON used the same # of calls
    # (isolates the compression effect from agent-loop nondeterminism).
    matched_off = matched_on = 0
    matched_n = 0
    outliers = []
    off_med = median([off_by_q[q]["prompt_tokens"] for q in qids])
    on_med = median([on_by_q[q]["prompt_tokens"] for q in qids])
    for q in qids:
        o, n_ = off_by_q[q], on_by_q[q]
        if o["calls"] == n_["calls"]:
            matched_off += o["prompt_tokens"]; matched_on += n_["prompt_tokens"]; matched_n += 1
        elif n_["calls"] > o["calls"]:
            outliers.append((q, o["calls"], n_["calls"], o["prompt_tokens"], n_["prompt_tokens"]))

    L.append("## Headline\n")
    L.append("_Token deltas are ON relative to OFF: **negative = fewer tokens (savings)**._\n")
    if off and on:
        L.append(f"- **Per-request compression (median prompt tokens/question): "
                 f"{off_med:,.0f} → {on_med:,.0f} ({pct(off_med, on_med)})**")
        if matched_n:
            L.append(f"- **Matched-trajectory subset ({matched_n}/{off['n']} questions where OFF and ON "
                     f"used the same # of calls): {matched_off:,} → {matched_on:,} "
                     f"({pct(matched_off, matched_on)})**, the cleanest isolation of the compression effect")
        L.append(f"- Raw total across ALL calls: {off['prompt_tokens']:,} → {on['prompt_tokens']:,} "
                 f"({pct(off['prompt_tokens'], on['prompt_tokens'])}) "
                 f", dominated by {len(outliers)} agent-loop outlier(s), see below")
        L.append(f"- Questions: {off['n']} | LLM calls OFF {off['calls']} / ON {on['calls']}")
        L.append(f"- Exact match: OFF {off['em']}/{off['n']} · ON {on['em']}/{on['n']}  "
                 f"| answer-contains-gold: OFF {off['contains']}/{off['n']} · ON {on['contains']}/{on['n']}")
        L.append(f"- Mean F1: OFF {off['f1']:.3f} · ON {on['f1']:.3f}")
        acc_note = ("no accuracy loss" if on["contains"] >= off["contains"]
                    else f"accuracy cost: −{off['contains']-on['contains']} on answer-contains, "
                         f"−{off['em']-on['em']} on exact-match")
        L.append(f"- **Accuracy vs savings:** {acc_note} (small-n, hard multihop; see per-question table)")
        L.append(f"- Images rendered (ON): {on['images']} across {on['compressed_calls']} compressed calls")
        L.append(f"- Regions imaged (ON): {dict(regions)}")
        L.append(f"- Wall time: OFF {off['wall_s']:.0f}s · ON {on['wall_s']:.0f}s "
                 f"(imaging adds render + vision-encode latency)\n")

    L.append("## Token usage per question (all OpenCode calls summed)\n")
    L.append("| qid | doc chars | OFF calls | OFF prompt tok | ON calls | ON prompt tok | Δ prompt tok | ON images |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    tot_off_pt = tot_on_pt = 0
    for q in qids:
        o, n_ = off_by_q[q], on_by_q[q]
        tot_off_pt += o["prompt_tokens"]; tot_on_pt += n_["prompt_tokens"]
        L.append(f"| {q} | {o['doc_chars']:,} | {o['calls']} | {o['prompt_tokens']:,} | "
                 f"{n_['calls']} | {n_['prompt_tokens']:,} | {pct(o['prompt_tokens'], n_['prompt_tokens'])} | {n_['images']} |")
    L.append(f"| **total** | | | **{tot_off_pt:,}** | | **{tot_on_pt:,}** | "
             f"**{pct(tot_off_pt, tot_on_pt)}** | |\n")

    L.append("## Correctness per question (ON vs OFF)\n")
    L.append("| qid | question | gold | OFF pred | OFF em/ct | ON pred | ON em/ct |")
    L.append("|---|---|---|---|:--:|---|:--:|")
    for q in qids:
        o, n_ = off_by_q[q], on_by_q[q]
        ql = (o["question"][:60] + "…") if len(o["question"]) > 60 else o["question"]
        L.append(f"| {q} | {ql} | {o['gold']} | {o['pred'][:32]} | {o['em']}/{o['contains']} | "
                 f"{n_['pred'][:32]} | {n_['em']}/{n_['contains']} |")
    L.append("")

    if outliers:
        L.append("## Agent-loop outliers (raw-total confound)\n")
        L.append("Questions where the ON agent ran **more tool-loop iterations** than OFF. Each extra "
                 "turn re-sends the *accumulating* imaged context, so cost compounds. This is trajectory "
                 "nondeterminism (the model chose to loop), not a per-request cost of compression, but it "
                 "is a real risk the design must bound (image budget across turns / history collapse).\n")
        L.append("| qid | OFF calls | ON calls | OFF tok | ON tok |")
        L.append("|---|---:|---:|---:|---:|")
        for q, oc, nc, ot, nt in outliers:
            L.append(f"| {q} | {oc} | {nc} | {ot:,} | {nt:,} |")
        L.append("")

    L.append("## Notes\n")
    L.append("- **Trajectory variance:** OpenCode is an autonomous agent; the number "
             "of LLM calls per question can differ between OFF and ON runs (tool-loop "
             "nondeterminism). Token totals are summed over *all* calls in each run, "
             "so a differing call count is part of the honest comparison; the per-call "
             "and per-request savings (see the main README A/B) isolate the compression "
             "effect from trajectory noise.")
    L.append("- **Correctness parity** is the key safety signal: imaging the context "
             "should not reduce answer accuracy. Compare the EM/contains columns ON vs OFF.")
    L.append("- **Instrument:** identical proxy for both conditions; OFF forwards bytes "
             "unchanged (`IMGCTX_ENABLED=0`) but still logs upstream-billed usage.")
    L.append("- Raw artifacts: `bench/hotpot_runs/<cond>/<qid>/` holds `documents.md`, "
             "`events.jsonl` (per-call usage + transform stats), and `stdout.txt` (trajectory).")
    L.append("")

    out = RUNS / "REPORT.md"
    out.write_text("\n".join(L))
    print(f"wrote {out}")
    # Also echo headline to stdout.
    if off and on:
        print(f"prompt tokens {off['prompt_tokens']:,} -> {on['prompt_tokens']:,} "
              f"({pct(off['prompt_tokens'], on['prompt_tokens'])})")


if __name__ == "__main__":
    main()
