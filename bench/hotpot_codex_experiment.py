"""HotpotQA A/B through the real Codex CLI + imgctx (native Responses OAuth relay).

Same read-a-doc-then-answer task as the opencode/claude HotpotQA harnesses, but
driven by `codex exec` against a ChatGPT subscription routed through imgctx. Codex
speaks the Responses API natively, so imgctx images the doc (which arrives as a
function_call_output tool result when codex cats the file) in place and streams the
native SSE back.

For each question we run codex twice: compression OFF (relay only, no imaging) and
ON (relay + imaging). The proxy stays in OAuth-relay mode in BOTH arms. OFF just
toggles IMGCTX_ENABLED=0. Every /responses call's usage (input/output + cache split
under input_tokens_details) and the full raw request/response bytes are captured to
disk per arm, so token/cost/compression can be inspected without a paid rerun.

Run (PAID, ChatGPT subscription):
  .venv/bin/python -m bench.hotpot_codex_experiment --n 1 --runs-dir hotpot_verify_runs/codex
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from bench._opencode_run import parse_final_answer, read_usage, start_proxy, stop_proxy
from bench.hotpot_experiment import build_documents, contains, em, f1
from bench._profiles import cost_for, profile_meta, resolve_profile

HERE = Path(__file__).resolve().parent
RUNS = HERE / "hotpot_codex_runs"
DATA_SRC = HERE / "hotpot_runs" / "data.json"  # reuse the fetched questions
PORT = 8819
MODEL = "gpt-5.4-mini"
AGENT = "codex"
BENCHMARK = "hotpot"

# Relay knobs, present in BOTH arms (not imaging flags): keep the OAuth relay live so
# OFF is relay-only (IMGCTX_ENABLED=0) and ON adds imaging. The per-region imaging
# config comes from bench._profiles (codex uses the OpenAI-aggressive profile; on
# HotpotQA the only imageable region is codex's ~13k-char system prompt).
RELAY_ENV = {"IMGCTX_CODEX_OAUTH": "1", "IMGCTX_DUMMY_KEY": "x"}

PROMPT_TEMPLATE = (
    "Read the file at this absolute path: {docs}\n"
    "Using ONLY the information in that file, answer the question as briefly as "
    "possible (a name, entity, number, or yes/no). Do not edit any files.\n"
    "Question: {question}\n"
    "Reply with exactly one final line formatted: FINAL ANSWER: <answer>"
)


def _proxy_env(cond: str) -> dict:
    """Relay knobs (both arms) + the agent's pinned per-region imaging profile."""
    env = dict(RELAY_ENV)
    prof = resolve_profile(AGENT, BENCHMARK, cond)
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


def load_questions(n: int) -> list[dict]:
    return json.loads(DATA_SRC.read_text())[:n]


def run_item(row: dict, qid: str, cond: str, timeout: int) -> dict:
    qdir = RUNS / cond / qid
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    (qdir / "documents.md").write_text(build_documents(row))
    docs = str((qdir / "documents.md").resolve())
    prompt = PROMPT_TEMPLATE.format(docs=docs, question=row["question"])

    log_path = qdir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(cond))
    try:
        out = run_codex(qdir, prompt, timeout=timeout)
    finally:
        stop_proxy(proc, PORT)
    (qdir / "stdout.txt").write_text(out)

    pred = parse_final_answer(out)
    gold = row["answer"]
    u = read_usage(log_path)
    cost = cost_for(AGENT, u)  # codex: simulated @ OpenAI gpt-5.4-mini list
    return {
        "cond": cond, "qid": qid, "question": row["question"],
        "gold": gold, "pred": pred,
        "em": em(pred, gold), "f1": round(f1(pred, gold), 3),
        "contains": contains(pred, gold),
        "duration_s": round(time.time() - t0, 1),
        "doc_chars": len((qdir / "documents.md").read_text()),
        "usage": u,
        **cost,
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--tag", default="")
    ap.add_argument("--runs-dir", default=None,
                    help="override output folder (default hotpot_codex_runs)")
    ap.add_argument("--port", type=int, default=8819,
                    help="proxy port (override for parallel runs so ports never collide)")
    args = ap.parse_args()

    global RUNS, PORT
    PORT = args.port
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
    RUNS.mkdir(parents=True, exist_ok=True)

    # Log the exact resolved profile + rate table so this run is reproducible/auditable.
    meta = profile_meta(AGENT, BENCHMARK)
    meta["model"] = MODEL
    (RUNS / f"run_meta{args.tag}.json").write_text(json.dumps(meta, indent=2))

    rows = load_questions(args.n)
    print(f"{len(rows)} HotpotQA questions; codex model={MODEL}", flush=True)

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
                  f"out={u.get('completion_tokens')} imgs={u.get('images')} "
                  f"f1={r.get('f1')} ct={r.get('contains')} err={r.get('is_error')}", flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
