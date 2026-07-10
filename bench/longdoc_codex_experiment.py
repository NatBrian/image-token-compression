"""Long-document single-shot A/B through the real Codex CLI + imgctx (Responses OAuth).

The Codex/ChatGPT-subscription counterpart to bench.longdoc_opencode_experiment and
bench.longdoc_claude_experiment. Same LongBench items (via the shared load_items),
same scoring, same read-once task shape; only the CLI (`codex exec`) and cost basis
differ. Each item is one large UNIQUE document read once, then answered (narrativeqa)
or summarized (gov_report).

Codex speaks the Responses API natively, so imgctx images the doc (which arrives as a
function_call_output tool result when codex cats the file) in place and streams the
native SSE back. For each item we run codex twice: compression OFF (relay only, no
imaging: IMGCTX_ENABLED=0) and ON (relay + the codex per-region imaging profile). The
proxy stays in OAuth-relay mode in BOTH arms. Every /responses call's usage and the
raw request/response bytes are captured to disk per arm.

Codex runs on a ChatGPT subscription (no provider-billed dollar field), so the dollar
figure is SIMULATED from the OpenAI gpt-5.4-mini list price via bench._profiles.

Run (PAID, ChatGPT subscription):
  .venv/bin/python -m bench.longdoc_codex_experiment --n 6 --config narrativeqa
  .venv/bin/python -m bench.longdoc_codex_experiment --n 4 --config gov_report
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from bench._opencode_run import parse_final_answer, read_usage, start_proxy, stop_proxy
# Reuse the exact data + scoring from the Claude longdoc harness so the instrument
# matches the opencode/claude longdoc drivers; only the runner + cost basis differ.
from bench.longdoc_claude_experiment import (
    best_score, gold_answers, load_items, PROMPT_TEMPLATE, SUMMARY_TEMPLATE,
)
from bench._profiles import cost_for, profile_meta, resolve_profile

HERE = Path(__file__).resolve().parent
RUNS = HERE / "longdoc_codex_runs"
PORT = 8821  # unique: distinct from every other bench proxy port
MODEL = "gpt-5.4-mini"
AGENT = "codex"

# Relay knobs, present in BOTH arms (not imaging flags): keep the OAuth relay live so
# OFF is relay-only (IMGCTX_ENABLED=0) and ON adds imaging. The per-region imaging
# config comes from bench._profiles keyed by the config (narrativeqa | gov_report).
RELAY_ENV = {"IMGCTX_CODEX_OAUTH": "1", "IMGCTX_DUMMY_KEY": "x"}


def _proxy_env(config: str, cond: str) -> dict:
    """Relay knobs (both arms) + the agent's pinned per-region imaging profile.

    For longdoc the benchmark key IS the config (narrativeqa | gov_report)."""
    env = dict(RELAY_ENV)
    prof = resolve_profile(AGENT, config, cond)
    if prof:
        env.update(prof)
    return env


def _codex_cmd(prompt: str) -> list[str]:
    base = f"http://127.0.0.1:{PORT}/v1"
    return [
        "codex", "exec", "--skip-git-repo-check",
        "-c", f'model="{MODEL}"',
        "-c", 'model_provider="imgctx"',
        "-c", 'model_providers.imgctx.name="imgctx"',
        "-c", f'model_providers.imgctx.base_url="{base}"',
        "-c", 'model_providers.imgctx.wire_api="responses"',
        "-c", 'model_providers.imgctx.env_key="IMGCTX_DUMMY_KEY"',
        prompt,
    ]


def run_codex(cwd: Path, prompt: str, timeout: int) -> str:
    import os
    env = dict(os.environ)
    env["IMGCTX_DUMMY_KEY"] = "x"  # env_key the codex provider resolves (imgctx overrides w/ OAuth)
    try:
        res = subprocess.run(_codex_cmd(prompt), cwd=str(cwd), env=env,
                             capture_output=True, text=True, timeout=timeout)
        return (res.stdout or "") + "\n" + (res.stderr or "")
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "") + "\n[TIMEOUT]"


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

    log_path = qdir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(config, cond))
    try:
        out = run_codex(qdir, prompt, timeout=timeout)
    finally:
        stop_proxy(proc, PORT)
    (qdir / "stdout.txt").write_text(out)

    pred = parse_final_answer(out)
    golds = gold_answers(row)
    e, ff, c = best_score(pred, golds)
    u = read_usage(log_path)
    cost = cost_for(AGENT, u)  # codex: simulated @ OpenAI gpt-5.4-mini list
    return {
        "cond": cond, "qid": qid, "config": config,
        "question": question, "gold": golds, "pred": pred,
        "em": e, "f1": ff, "contains": c,
        "duration_s": round(time.time() - t0, 1),
        "doc_chars": len(str(row["context"])),
        "usage": u,
        **cost,
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="narrativeqa",
                    choices=["narrativeqa", "gov_report"],
                    help="LongBench config: narrativeqa | gov_report")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--max-chars", type=int, default=90000)
    ap.add_argument("--tag", default="",
                    help="suffix for the results file so a different model does not clobber")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default longdoc_codex_runs), "
                         "so a different model/provider never clobbers a prior run")
    ap.add_argument("--port", type=int, default=8821,
                    help="proxy port (override for parallel runs so ports never collide)")
    args = ap.parse_args()

    global RUNS, PORT
    PORT = args.port
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
    RUNS.mkdir(parents=True, exist_ok=True)

    # Log the exact resolved profile + rate table so this run is reproducible/auditable.
    meta = profile_meta(AGENT, args.config)
    meta["model"] = MODEL
    (RUNS / f"run_meta_{args.config}{args.tag}.json").write_text(json.dumps(meta, indent=2))

    rows = load_items(args.config, args.n, args.max_chars)
    print(f"{len(rows)} {args.config} items loaded; codex model={MODEL} "
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
                  f"out={u.get('completion_tokens')} imgs={u.get('images')} "
                  f"f1={r.get('f1')} ct={r.get('contains')} err={r.get('is_error')}",
                  flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
