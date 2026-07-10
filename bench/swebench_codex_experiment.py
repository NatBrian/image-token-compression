"""SWE-bench Lite A/B through the real Codex CLI + imgctx (native Responses OAuth relay).

The Codex/OAuth counterpart to bench.swebench_opencode_experiment (mimo) and
bench.swebench_claude_experiment (Anthropic). Same instance selection and repo
checkout machinery (imported directly from the Claude harness), same agentic
"fix the issue" task, only the CLI and provider differ. As in the other SWE-bench
harnesses we do NOT execute the repo's tests (no Docker here); the deliverable is
the token/cache/cost reduction plus the captured git diff for optional later grading.

Codex speaks the Responses API natively over a ChatGPT subscription routed through
imgctx, so tool results (the files codex cats/edits) get imaged in place and the
native SSE is streamed back. For each instance we run codex twice: compression OFF
(relay only, IMGCTX_ENABLED=0) and ON (relay + imaging). The proxy stays in
OAuth-relay mode in BOTH arms. Every /responses call's usage (input/output + cache
split) and the full raw request/response bytes are captured per arm, so
token/cost/compression can be inspected without a paid rerun.

Run (PAID, ChatGPT subscription):
  .venv/bin/python -m bench.swebench_codex_experiment --n 5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from bench._opencode_run import read_usage, start_proxy, stop_proxy
# Reuse the Claude harness's selection + checkout so the instances are identical
# across all SWE-bench drivers.
from bench.swebench_claude_experiment import (
    PROMPT_TEMPLATE, _run, ensure_base_checkout, select_instances,
)
from bench._profiles import cost_for, profile_meta, resolve_profile

HERE = Path(__file__).resolve().parent
RUNS = HERE / "swebench_codex_runs"
PORT = 8820  # distinct from the other benchmarks' ports
MODEL = "gpt-5.4-mini"
AGENT = "codex"
BENCHMARK = "swebench"

# Relay knobs, present in BOTH arms (not imaging flags): keep the OAuth relay live so
# OFF is relay-only (IMGCTX_ENABLED=0) and ON adds imaging. The per-region imaging
# config comes from bench._profiles (codex uses the OpenAI-aggressive profile).
RELAY_ENV = {"IMGCTX_CODEX_OAUTH": "1", "IMGCTX_DUMMY_KEY": "x"}


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
    env = dict(os.environ)
    env["IMGCTX_DUMMY_KEY"] = "x"  # env_key the codex provider resolves (imgctx overrides w/ OAuth)
    try:
        res = subprocess.run(_codex_cmd(prompt), cwd=str(cwd), env=env,
                             capture_output=True, text=True, timeout=timeout)
        return (res.stdout or "") + "\n" + (res.stderr or "")
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "") + "\n[TIMEOUT]"


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

    # log_path is per-(cond, instance): start_proxy points IMGCTX_CAPTURE_DIR at
    # repo_dir/capture, so raw request/response bytes never collide across arms.
    log_path = repo_dir / "events.jsonl"
    enabled = cond == "on"

    t0 = time.time()
    proc = start_proxy(enabled, PORT, log_path, extra_env=_proxy_env(cond))
    try:
        out = run_codex(repo_dir, prompt, timeout=timeout)
    finally:
        stop_proxy(proc, PORT)
    (repo_dir / "stdout.txt").write_text(out)

    # Capture the produced patch. Codex uses -c overrides (no config file written into
    # the repo), so there is nothing to revert before diffing.
    rc, diff = _run(["git", "diff"], cwd=repo_dir, timeout=60)
    (repo_dir / "model.patch").write_text(diff)

    u = read_usage(log_path)
    cost = cost_for(AGENT, u)  # codex: simulated @ OpenAI gpt-5.4-mini list
    return {
        "cond": cond, "instance_id": inst["instance_id"], "repo": inst["repo"],
        "duration_s": round(time.time() - t0, 1),
        "patch_chars": len(diff), "produced_patch": bool(diff.strip()),
        "usage": u,
        **cost,
        "is_error": u["calls"] == 0 or "[TIMEOUT]" in out,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--tag", default="")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default swebench_codex_runs)")
    ap.add_argument("--port", type=int, default=8820,
                    help="proxy port (override for parallel runs so ports never collide)")
    args = ap.parse_args()

    global RUNS, PORT
    PORT = args.port
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
    sel_path = RUNS / "instances.json"

    RUNS.mkdir(parents=True, exist_ok=True)

    # Log the exact resolved profile + rate table so this run is reproducible/auditable.
    meta = profile_meta(AGENT, BENCHMARK)
    meta["model"] = MODEL
    (RUNS / f"run_meta{args.tag}.json").write_text(json.dumps(meta, indent=2))

    if sel_path.exists():
        insts = json.loads(sel_path.read_text())[: args.n]
    else:
        insts = select_instances(args.n)
        sel_path.write_text(json.dumps(insts, indent=2))
    print(f"{len(insts)} SWE-bench instances: "
          f"{', '.join(i['instance_id'] for i in insts)}; codex model={MODEL}",
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
                  f"out={u.get('completion_tokens')} imgs={u.get('images')} "
                  f"patch={r.get('produced_patch')} err={r.get('is_error')}", flush=True)
            results.append(r)
            results_path.write_text(json.dumps(results, indent=2))
            time.sleep(1.0)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
