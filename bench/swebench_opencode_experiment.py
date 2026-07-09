"""SWE-bench Lite A/B through the real OpenCode CLI + imgctx (mimo-v2.5-free path).

The OpenCode/mimo counterpart to bench.swebench_experiment (which used Claude Code).
Same instance selection and repo-checkout machinery (imported directly), same
agentic "fix the issue" task, only the CLI and provider differ. As in the Claude
harness we do NOT execute the repo's tests (no Docker here); the deliverable is the
token/cache/cost reduction plus the captured git diff for optional later grading.

mimo-v2.5-free is FREE, so there is no provider-billed dollar figure. We record real
tokens including the endpoint's cache split (cached_tokens = cache-read,
cache_write_tokens = cache-write). Dollars are a SEPARATE, clearly labelled
simulation (bench.opencode_cost_breakdown).

This is the re-read regime (a repo context revisited across many agentic turns), the
same shape that cost more on Anthropic. On the OpenCode/mimo endpoint, which reports
no cache-write premium, the question is whether that loss disappears.

Run:
  .venv/bin/python -m bench.swebench_opencode_experiment --n 5
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from bench._opencode_run import read_usage, run_opencode, start_proxy, stop_proxy, write_config
# Reuse the Claude harness's selection + checkout so the instances are identical.
from bench.swebench_claude_experiment import (
    PROMPT_TEMPLATE, _run, ensure_base_checkout, select_instances,
)

HERE = Path(__file__).resolve().parent
RUNS = HERE / "swebench_opencode_runs"
PORT = 8812  # distinct from the other benchmarks' ports

# Match the Claude SWE-bench ON arm: image tools + tool results + history, keep the
# system prompt as text (it carries the cwd/tool rules).
ON_ENV = {"IMGCTX_SYSTEM": "0"}

# Set from CLI in main(). Defaults keep the mimo/zen behaviour.
MODEL = "opencode/mimo-v2.5-free"
PROVIDER = "opencode"
UPSTREAM = None
API_KEY = None
IMGCTX_MODELS = None


def _proxy_env(enabled: bool) -> dict | None:
    env = dict(ON_ENV) if enabled else {}
    if UPSTREAM:
        env["IMGCTX_UPSTREAM_BASE"] = UPSTREAM
    if IMGCTX_MODELS:
        env["IMGCTX_MODELS"] = IMGCTX_MODELS
    return env or None


def _models_block() -> dict | None:
    if PROVIDER == "opencode":
        return None
    bare = MODEL.split("/", 1)[-1]
    return {bare: {"id": bare, "name": bare, "tool_call": True,
                   "limit": {"context": 128000, "output": 8192}}}


def fresh_worktree(inst: dict, cond: str) -> Path:
    base = ensure_base_checkout(inst)
    dst = RUNS / cond / inst["instance_id"]
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base, dst)
    return dst


def run_agent(inst: dict, cond: str, timeout: int) -> dict:
    repo_dir = fresh_worktree(inst, cond)
    prompt = PROMPT_TEMPLATE.format(repo=inst["repo"], problem=inst["problem_statement"])

    cfg_path = write_config(repo_dir / "opencode.json", PORT, provider=PROVIDER,
                            api_key=API_KEY, models=_models_block())
    log_path = repo_dir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(enabled))
    try:
        out = run_opencode(repo_dir, prompt, cfg_path, timeout=timeout, model=MODEL)
    finally:
        stop_proxy(proc, PORT)
    (repo_dir / "stdout.txt").write_text(out)

    # Capture the produced patch (opencode.json is inside the repo dir; exclude it).
    _run(["git", "checkout", "--", "opencode.json"], cwd=repo_dir, timeout=30)
    rc, diff = _run(["git", "diff"], cwd=repo_dir, timeout=60)
    (repo_dir / "model.patch").write_text(diff)

    u = read_usage(log_path)
    return {
        "cond": cond, "instance_id": inst["instance_id"], "repo": inst["repo"],
        "duration_s": round(time.time() - t0, 1),
        "patch_chars": len(diff), "produced_patch": bool(diff.strip()),
        "usage": u,
        "cost_usd": u["cost_usd"],  # real, provider-billed if the endpoint reports usage.cost
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--model", default="opencode/mimo-v2.5-free")
    ap.add_argument("--provider", default="opencode")
    ap.add_argument("--upstream", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--imgctx-models", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default swebench_opencode_runs), "
                         "so a different model/provider never clobbers a prior run")
    args = ap.parse_args()

    global MODEL, PROVIDER, UPSTREAM, API_KEY, IMGCTX_MODELS, RUNS
    MODEL, PROVIDER, UPSTREAM = args.model, args.provider, args.upstream
    API_KEY, IMGCTX_MODELS = args.api_key, args.imgctx_models
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
    sel_path = RUNS / "instances.json"

    RUNS.mkdir(parents=True, exist_ok=True)
    if sel_path.exists():
        insts = json.loads(sel_path.read_text())[: args.n]
    else:
        insts = select_instances(args.n)
        sel_path.write_text(json.dumps(insts, indent=2))
    print(f"{len(insts)} SWE-bench instances: "
          f"{', '.join(i['instance_id'] for i in insts)}; model={MODEL} provider={PROVIDER}",
          flush=True)

    results: list[dict] = []
    results_path = RUNS / f"results{args.tag}.json"
    for i, inst in enumerate(insts):
        for cond in ("off", "on"):
            print(f"[{i+1}/{len(insts)}] {inst['instance_id']} {cond} ...", flush=True)
            try:
                r = run_agent(inst, cond, args.timeout)
            except Exception as ex:
                r = {"cond": cond, "instance_id": inst["instance_id"],
                     "harness_error": f"{type(ex).__name__}:{ex}",
                     "usage": read_usage(RUNS / cond / inst["instance_id"] / "events.jsonl"),
                     "cost_usd": None, "is_error": True}
            u = r.get("usage", {})
            print(f"    calls={u.get('calls')} cmp={u.get('compressed_calls')} "
                  f"prompt={u.get('prompt_tokens')} read={u.get('cached_tokens')} "
                  f"write={u.get('cache_write_tokens')} out={u.get('completion_tokens')} "
                  f"patch={r.get('produced_patch')} err={r.get('is_error')}", flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
