"""Long-document single-shot A/B through the real OpenCode CLI + imgctx (mimo path).

The OpenCode/mimo-v2.5-free counterpart to bench.longdoc_experiment (which used
Claude Code). Same LongBench items, same scoring, same read-once task shape; only
the CLI and provider differ. Each item is one large UNIQUE document read once.

Because mimo-v2.5-free is FREE, there is NO provider-billed dollar figure. We record
the real token usage including the endpoint's cache split (cached_tokens =
cache-read, cache_write_tokens = cache-write); dollars are a SEPARATE, clearly
labelled simulation (bench.opencode_cost_breakdown).

ON images ONLY the read-once doc (IMGCTX_SYSTEM=0, IMGCTX_TOOLS=0), matching the
Claude longdoc arm.

Run:
  .venv/bin/python -m bench.longdoc_opencode_experiment --n 6 --config narrativeqa
  .venv/bin/python -m bench.longdoc_opencode_experiment --n 4 --config gov_report
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from bench._opencode_run import (
    parse_final_answer, read_usage, run_opencode, start_proxy, stop_proxy, write_config,
)
# Reuse the exact data + scoring from the Claude longdoc harness so the instrument
# matches; only the runner (opencode vs claude) and cost basis differ.
from bench.longdoc_experiment import (
    best_score, gold_answers, load_items, PROMPT_TEMPLATE, SUMMARY_TEMPLATE,
)

HERE = Path(__file__).resolve().parent
RUNS = HERE / "longdoc_opencode_runs"
PORT = 8811  # distinct from the Claude longdoc ports and the hotpot opencode port

# ON images only the unique doc; system+tools stay text (mirror the Claude arm).
ON_ENV = {"IMGCTX_SYSTEM": "0", "IMGCTX_TOOLS": "0"}


def run_item(row: dict, qid: str, cond: str, config: str, timeout: int) -> dict:
    qdir = RUNS / cond / qid
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    docs = qdir / "document.md"
    docs.write_text(str(row["context"]))

    question = str(row.get("input", "")).strip()
    tmpl = SUMMARY_TEMPLATE if config == "gov_report" else PROMPT_TEMPLATE
    prompt = tmpl.format(docs=str(docs.resolve()), question=question)

    cfg_path = write_config(qdir / "opencode.json", PORT)
    log_path = qdir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=ON_ENV if enabled else None)
    try:
        out = run_opencode(qdir, prompt, cfg_path, timeout=timeout)
    finally:
        stop_proxy(proc, PORT)
    (qdir / "stdout.txt").write_text(out)

    pred = parse_final_answer(out)
    golds = gold_answers(row)
    e, ff, c = best_score(pred, golds)
    u = read_usage(log_path)
    return {
        "cond": cond, "qid": qid, "config": config,
        "question": question, "gold": golds, "pred": pred,
        "em": e, "f1": ff, "contains": c,
        "duration_s": round(time.time() - t0, 1),
        "doc_chars": len(str(row["context"])),
        "usage": u,
        "cost_usd": None,  # free model: no provider-billed cost. Sim only, separate script.
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--config", default="narrativeqa",
                    help="LongBench config: narrativeqa | gov_report | ...")
    ap.add_argument("--timeout", type=int, default=360)
    ap.add_argument("--max-chars", type=int, default=90000)
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    rows = load_items(args.config, args.n, args.max_chars)
    print(f"{len(rows)} {args.config} items loaded "
          f"(avg doc {sum(len(str(r['context'])) for r in rows)//max(len(rows),1):,} chars)",
          flush=True)

    results: list[dict] = []
    results_path = RUNS / f"results_{args.config}.json"
    for i, row in enumerate(rows):
        qid = f"q{i:02d}"
        for cond in ("off", "on"):
            print(f"[{i+1}/{len(rows)}] {qid} {cond} ...", flush=True)
            try:
                r = run_item(row, qid, cond, args.config, args.timeout)
            except Exception as ex:
                r = {"cond": cond, "qid": qid, "config": args.config,
                     "harness_error": f"{type(ex).__name__}:{ex}",
                     "usage": read_usage(RUNS / cond / qid / "events.jsonl"),
                     "cost_usd": None, "is_error": True}
            u = r.get("usage", {})
            print(f"    calls={u.get('calls')} cmp={u.get('compressed_calls')} "
                  f"prompt={u.get('prompt_tokens')} read={u.get('cached_tokens')} "
                  f"write={u.get('cache_write_tokens')} out={u.get('completion_tokens')} "
                  f"f1={r.get('f1')} ct={r.get('contains')} err={r.get('is_error')}",
                  flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
