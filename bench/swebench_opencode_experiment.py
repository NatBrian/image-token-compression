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
from bench.swebench_experiment import (
    PROMPT_TEMPLATE, _run, ensure_base_checkout, select_instances,
)

HERE = Path(__file__).resolve().parent
RUNS = HERE / "swebench_opencode_runs"
SEL_PATH = RUNS / "instances.json"
PORT = 8812  # distinct from the other benchmarks' ports

# Match the Claude SWE-bench ON arm: image tools + tool results + history, keep the
# system prompt as text (it carries the cwd/tool rules).
ON_ENV = {"IMGCTX_SYSTEM": "0"}


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

    cfg_path = write_config(repo_dir / "opencode.json", PORT)
    log_path = repo_dir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=ON_ENV if enabled else None)
    try:
        out = run_opencode(repo_dir, prompt, cfg_path, timeout=timeout)
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
        "cost_usd": None,  # free model: no provider-billed cost. Sim only, separate script.
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=420)
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    if SEL_PATH.exists():
        insts = json.loads(SEL_PATH.read_text())[: args.n]
    else:
        insts = select_instances(args.n)
        SEL_PATH.write_text(json.dumps(insts, indent=2))
    print(f"{len(insts)} SWE-bench instances: "
          f"{', '.join(i['instance_id'] for i in insts)}", flush=True)

    results: list[dict] = []
    results_path = RUNS / "results.json"
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
