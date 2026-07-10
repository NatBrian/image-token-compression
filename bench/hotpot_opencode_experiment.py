"""HotpotQA A/B through the OpenCode CLI + imgctx, model-parameterised.

Uses the shared bench._opencode_run helper (isolated OPENCODE_CONFIG + per-item
proxy that captures the endpoint's full cache split), so it works for both the
zen/mimo path and the OpenAI (api key) path routed to api.openai.com through the
proxy. Reuses the HotpotQA questions + scoring from bench.hotpot_experiment.

Run (mimo, free):
  .venv/bin/python -m bench.hotpot_opencode_experiment --n 1
Run (OpenAI gpt-4o-mini, PAID, real cost + real cache):
  .venv/bin/python -m bench.hotpot_opencode_experiment --n 1 \
      --model openai/gpt-4o-mini --provider openai --upstream https://api.openai.com/v1 --tag _gpt4omini
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
from bench.hotpot_experiment import build_documents, contains, em, f1

HERE = Path(__file__).resolve().parent
RUNS = HERE / "hotpot_opencode_runs"
DATA_SRC = HERE / "hotpot_runs" / "data.json"  # reuse the fetched questions
PORT = 8813

# Match the Claude HotpotQA ON arm: image tools + tool results + history, keep the
# system prompt as text.
ON_ENV = {"IMGCTX_SYSTEM": "0"}

PROMPT_TEMPLATE = (
    "Read the file at this absolute path: {docs}\n"
    "Using ONLY the information in that file, answer the question as briefly as "
    "possible (a name, entity, number, or yes/no). Do not edit any files.\n"
    "Question: {question}\n"
    "Reply with exactly one final line formatted: FINAL ANSWER: <answer>"
)

# Config set from CLI (defaults keep mimo behaviour).
MODEL = "opencode/mimo-v2.5-free"
PROVIDER = "opencode"
UPSTREAM = None
API_KEY = None
IMGCTX_MODELS = None
OAUTH = False  # ChatGPT OAuth relay (opencode -> imgctx -> chatgpt.com codex backend)


def _proxy_env(enabled: bool) -> dict | None:
    env = dict(ON_ENV) if enabled else {}
    # The OAuth relay must stay ON in BOTH arms -- OFF disables imaging, not the relay,
    # so the OFF arm is "relay only" (no compression) and ON is "relay + compression".
    if OAUTH:
        env["IMGCTX_OPENAI_OAUTH"] = "1"
    if UPSTREAM:
        env["IMGCTX_UPSTREAM_BASE"] = UPSTREAM
    if IMGCTX_MODELS:
        env["IMGCTX_MODELS"] = IMGCTX_MODELS
    return env or None


def _models_block() -> dict | None:
    """For a custom provider, force tool_call:true so the agent can use the Read tool
    (the doc arrives as an imageable tool_result)."""
    if PROVIDER == "opencode":
        return None
    bare = MODEL.split("/", 1)[-1]
    return {bare: {"id": bare, "name": bare, "tool_call": True,
                   "limit": {"context": 128000, "output": 8192}}}


def load_questions(n: int) -> list[dict]:
    rows = json.loads(DATA_SRC.read_text())
    return rows[:n]


def run_item(row: dict, qid: str, cond: str, timeout: int) -> dict:
    qdir = RUNS / cond / qid
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    (qdir / "documents.md").write_text(build_documents(row))
    docs = str((qdir / "documents.md").resolve())
    prompt = PROMPT_TEMPLATE.format(docs=docs, question=row["question"])

    cfg_path = write_config(qdir / "opencode.json", PORT, provider=PROVIDER,
                            api_key=API_KEY, models=_models_block())
    log_path = qdir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(enabled))
    try:
        out = run_opencode(qdir, prompt, cfg_path, timeout=timeout, model=MODEL)
    finally:
        stop_proxy(proc, PORT)
    (qdir / "stdout.txt").write_text(out)

    pred = parse_final_answer(out)
    gold = row["answer"]
    u = read_usage(log_path)
    return {
        "cond": cond, "qid": qid, "question": row["question"],
        "gold": gold, "pred": pred,
        "em": em(pred, gold), "f1": round(f1(pred, gold), 3),
        "contains": contains(pred, gold),
        "duration_s": round(time.time() - t0, 1),
        "doc_chars": len((qdir / "documents.md").read_text()),
        "usage": u,
        "cost_usd": u["cost_usd"],  # real, provider-billed if the endpoint reports usage.cost
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--model", default="opencode/mimo-v2.5-free")
    ap.add_argument("--provider", default="opencode")
    ap.add_argument("--upstream", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--imgctx-models", default=None,
                    help="override IMGCTX_MODELS allowlist, e.g. to add 'kimi'")
    ap.add_argument("--tag", default="")
    ap.add_argument("--oauth", action="store_true",
                    help="route opencode through the ChatGPT OAuth relay (imgctx_openai "
                         "provider + IMGCTX_OPENAI_OAUTH=1). Defaults model to "
                         "imgctx-openai/gpt-5.4-mini and apiKey to a dummy sentinel.")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default hotpot_opencode_runs), "
                         "so a different model/provider never clobbers a prior run")
    args = ap.parse_args()

    global MODEL, PROVIDER, UPSTREAM, API_KEY, IMGCTX_MODELS, RUNS, OAUTH
    MODEL, PROVIDER, UPSTREAM = args.model, args.provider, args.upstream
    API_KEY, IMGCTX_MODELS = args.api_key, args.imgctx_models
    if args.oauth:
        OAUTH = True
        if args.provider == "opencode":
            PROVIDER = "imgctx-openai"
        if args.model == "opencode/mimo-v2.5-free":
            MODEL = "imgctx-openai/gpt-5.4-mini"
        if not API_KEY:
            API_KEY = "oauth-relay"
    if args.runs_dir:
        RUNS = HERE / args.runs_dir

    RUNS.mkdir(parents=True, exist_ok=True)
    rows = load_questions(args.n)
    print(f"{len(rows)} HotpotQA questions; model={MODEL} provider={PROVIDER}", flush=True)

    results: list[dict] = []
    results_path = RUNS / f"results{args.tag}.json"
    for i, row in enumerate(rows):
        qid = f"q{i:02d}"
        for cond in ("off", "on"):
            print(f"[{i+1}/{len(rows)}] {qid} {cond} ...", flush=True)
            try:
                r = run_item(row, qid, cond, args.timeout)
            except Exception as ex:
                r = {"cond": cond, "qid": qid,
                     "harness_error": f"{type(ex).__name__}:{ex}",
                     "usage": read_usage(RUNS / cond / qid / "events.jsonl"),
                     "cost_usd": None, "is_error": True}
            u = r.get("usage", {})
            print(f"    calls={u.get('calls')} cmp={u.get('compressed_calls')} "
                  f"prompt={u.get('prompt_tokens')} read={u.get('cached_tokens')} "
                  f"write={u.get('cache_write_tokens')} out={u.get('completion_tokens')} "
                  f"f1={r.get('f1')} ct={r.get('contains')} err={r.get('is_error')}", flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
