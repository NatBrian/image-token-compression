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
    is_run_error, parse_final_answer, read_usage, run_opencode, start_proxy,
    stop_proxy, write_config,
)
from bench._profiles import cost_for, profile_meta, resolve_profile
# Reuse the exact data + scoring from the Claude longdoc harness so the instrument
# matches; only the runner (opencode vs claude) and cost basis differ.
from bench.longdoc_claude_experiment import (
    best_score, gold_answers, load_items, PROMPT_TEMPLATE, SUMMARY_TEMPLATE,
)

HERE = Path(__file__).resolve().parent
RUNS = HERE / "longdoc_opencode_runs"
PORT = 8811  # distinct from the Claude longdoc ports and the hotpot opencode port
AGENT = "mimo"  # imaging/pricing profile family; BENCHMARK key is the --config

# Set from CLI in main(). Defaults keep the mimo/zen behaviour.
MODEL = "opencode/mimo-v2.5-free"
PROVIDER = "opencode"
UPSTREAM = None  # None => proxy's default upstream (zen). Set for OpenAI.
API_KEY = None
IMGCTX_MODELS = None


def _proxy_env(config: str, cond: str) -> dict:
    """Per-region imaging profile for (mimo, config) + non-imaging upstream knobs."""
    env = dict(resolve_profile(AGENT, config, cond) or {})
    if UPSTREAM:
        env["IMGCTX_UPSTREAM_BASE"] = UPSTREAM
    if IMGCTX_MODELS:
        env["IMGCTX_MODELS"] = IMGCTX_MODELS
    return env


def _models_block() -> dict | None:
    if PROVIDER == "opencode":
        return None
    bare = MODEL.split("/", 1)[-1]
    return {bare: {"id": bare, "name": bare, "tool_call": True,
                   "limit": {"context": 128000, "output": 8192}}}


def run_item(row: dict, qid: str, cond: str, config: str, timeout: int) -> dict:
    # Namespace per-item dirs by CONFIG: multiple configs share the same qid (q00,
    # q01...), so without the config prefix a later config's run would rmtree and
    # clobber an earlier one's raw request/response capture in the same --runs-dir.
    qdir = RUNS / cond / f"{config}-{qid}"
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    docs = qdir / "document.md"
    docs.write_text(str(row["context"]))

    question = str(row.get("input", "")).strip()
    tmpl = SUMMARY_TEMPLATE if config == "gov_report" else PROMPT_TEMPLATE
    prompt = tmpl.format(docs=str(docs.resolve()), question=question)

    cfg_path = write_config(qdir / "opencode.json", PORT, provider=PROVIDER,
                            api_key=API_KEY, models=_models_block())
    log_path = qdir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(config, cond))
    try:
        out = run_opencode(qdir, prompt, cfg_path, timeout=timeout, model=MODEL)
    finally:
        stop_proxy(proc, PORT)
    (qdir / "stdout.txt").write_text(out)

    pred = parse_final_answer(out)
    golds = gold_answers(row)
    e, ff, c = best_score(pred, golds)
    u = read_usage(log_path)
    cost = cost_for(AGENT, u)  # mimo: simulated @ Xiaomi MiMo-V2.5 list
    return {
        "cond": cond, "qid": qid, "config": config,
        "question": question, "gold": golds, "pred": pred,
        "em": e, "f1": ff, "contains": c,
        "duration_s": round(time.time() - t0, 1),
        "doc_chars": len(str(row["context"])),
        "usage": u,
        **cost,
        "is_error": is_run_error(u, out),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--config", default="narrativeqa",
                    help="LongBench config: narrativeqa | gov_report | ...")
    ap.add_argument("--timeout", type=int, default=360)
    ap.add_argument("--max-chars", type=int, default=90000)
    ap.add_argument("--model", default="opencode/mimo-v2.5-free")
    ap.add_argument("--provider", default="opencode",
                    help="opencode (zen/mimo) or openai (api.openai.com via proxy)")
    ap.add_argument("--upstream", default=None,
                    help="IMGCTX_UPSTREAM_BASE for the proxy, e.g. https://api.openai.com/v1")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--imgctx-models", default=None)
    ap.add_argument("--tag", default="",
                    help="suffix for the results file so a different model does not clobber")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default longdoc_opencode_runs), "
                         "so a different model/provider never clobbers a prior run")
    ap.add_argument("--port", type=int, default=8811,
                    help="proxy port (override for parallel runs so ports never collide)")
    args = ap.parse_args()

    global MODEL, PROVIDER, UPSTREAM, API_KEY, IMGCTX_MODELS, RUNS, PORT
    PORT = args.port
    MODEL, PROVIDER, UPSTREAM = args.model, args.provider, args.upstream
    API_KEY, IMGCTX_MODELS = args.api_key, args.imgctx_models
    if args.runs_dir:
        RUNS = HERE / args.runs_dir

    RUNS.mkdir(parents=True, exist_ok=True)
    meta = profile_meta(AGENT, args.config)
    meta["model"] = MODEL
    (RUNS / f"run_meta_{args.config}{args.tag}.json").write_text(json.dumps(meta, indent=2))
    rows = load_items(args.config, args.n, args.max_chars)
    print(f"{len(rows)} {args.config} items loaded "
          f"(avg doc {sum(len(str(r['context'])) for r in rows)//max(len(rows),1):,} chars)",
          flush=True)

    results: list[dict] = []
    results_path = RUNS / f"results_{args.config}{args.tag}.json"
    for i, row in enumerate(rows):
        qid = f"q{i:02d}"
        for cond in ("off", "on"):
            print(f"[{i+1}/{len(rows)}] {qid} {cond} ...", flush=True)
            try:
                r = run_item(row, qid, cond, args.config, args.timeout)
            except Exception as ex:
                r = {"cond": cond, "qid": qid, "config": args.config,
                     "harness_error": f"{type(ex).__name__}:{ex}",
                     "usage": read_usage(RUNS / cond / f"{args.config}-{qid}" / "events.jsonl"),
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
