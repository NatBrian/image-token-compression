"""SWE-bench Lite A/B harness for Claude Code + imgctx (Anthropic Messages path).

For each selected instance we shallow-fetch the repo at its base commit and run the
real Claude Code CLI agentically twice: once through the imgctx proxy with
compression ON, once through an identical passthrough proxy with it OFF. Every API
call, the full event trajectory (stream-json), token usage, produced diff, and
wall-clock are recorded so the run can be audited and priced afterwards.

We do NOT execute the repo's tests (no Docker on this box); the deliverable is the
token/cost reduction plus the captured patch for optional later grading.

Usage:
  python -m bench.swebench_claude_experiment --n 10           # full run
  python -m bench.swebench_claude_experiment --select-only    # just pick + save instances
  python -m bench.swebench_claude_experiment --n 1 --instances psf__requests-...  # single
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from bench._profiles import cost_for, profile_meta, resolve_profile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "swebench_claude_runs"
REPOS = RUNS / "_repos_cache"
SEL_PATH = RUNS / "instances.json"
AGENT = "claude"
BENCHMARK = "swebench"

# NO manual pricing. Dollars come ONLY from Claude Code's own reported total_cost_usd
# (result event). We never convert tokens to dollars with an assumed rate table.

# Small / fast-cloning repos so a shallow single-commit fetch stays light.
PREFERRED_REPOS = ["psf/requests", "pallets/flask", "pylint-dev/pylint", "pytest-dev/pytest"]

# ON arm = the Anthropic-loop cost-aware profile from bench._profiles: keep the
# STATIC prefix (system + tool DOCS) as TEXT so Anthropic native caching reads it at
# 0.1x. Imaging the static tool-doc slab was the verified +26% cost driver (it
# inflates the one-time cache-WRITE). Only first-appearance huge tool_results image;
# no churning history-collapse. (Corrected from the earlier IMGCTX_TOOLS=1 config.)
_ON_REGION = {k: v for k, v in (resolve_profile(AGENT, BENCHMARK, "on") or {}).items()
              if k != "IMGCTX_ENABLED"}
PROXIES = {
    "off": {"port": 8788, "enabled": "0", "env": {}},
    "on": {"port": 8787, "enabled": "1", "env": _ON_REGION},
}

PROMPT_TEMPLATE = (
    "You are working inside the `{repo}` repository at its current checkout. "
    "Resolve the GitHub issue below by editing the repository's source code to fix "
    "the described bug. Make the smallest change that fixes it. Do NOT run the test "
    "suite and do NOT edit test files; just apply the source fix and then stop.\n\n"
    "<issue>\n{problem}\n</issue>\n"
)


# --------------------------------------------------------------------------- #
# instance selection
# --------------------------------------------------------------------------- #
def fetch_rows(total: int = 300) -> list[dict]:
    base = ("https://datasets-server.huggingface.co/rows?dataset=princeton-nlp/"
            "SWE-bench_Lite&config=default&split=test")
    rows: list[dict] = []
    for off in range(0, total, 100):
        u = f"{base}&offset={off}&length=100"
        d = json.load(urllib.request.urlopen(u, timeout=60))
        rows += [r["row"] for r in d["rows"]]
    return rows


def select_instances(n: int) -> list[dict]:
    rows = fetch_rows(300)
    keep = ["instance_id", "repo", "base_commit", "problem_statement", "patch",
            "FAIL_TO_PASS", "PASS_TO_PASS", "version"]
    picked: list[dict] = []
    # Round-robin across preferred small repos for variety, deterministic order.
    by_repo: dict[str, list[dict]] = {r: [] for r in PREFERRED_REPOS}
    for row in rows:
        if row["repo"] in by_repo:
            by_repo[row["repo"]].append(row)
    for lst in by_repo.values():
        lst.sort(key=lambda r: r["instance_id"])
    i = 0
    while len(picked) < n and any(by_repo.values()):
        repo = PREFERRED_REPOS[i % len(PREFERRED_REPOS)]
        if by_repo[repo]:
            row = by_repo[repo].pop(0)
            picked.append({k: row.get(k) for k in keep})
        i += 1
        if i > 10000:
            break
    return picked


# --------------------------------------------------------------------------- #
# repo checkout
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def ensure_base_checkout(inst: dict) -> Path:
    """Shallow-fetch the repo at its base commit once into a cache dir."""
    cache = REPOS / inst["instance_id"]
    if (cache / ".git").exists():
        return cache
    cache.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{inst['repo']}.git"
    _run(["git", "init", "-q"], cwd=cache)
    _run(["git", "remote", "add", "origin", url], cwd=cache)
    rc, out = _run(["git", "fetch", "-q", "--depth", "1", "origin", inst["base_commit"]],
                   cwd=cache, timeout=600)
    if rc != 0:
        raise RuntimeError(f"fetch failed for {inst['instance_id']}: {out[-500:]}")
    _run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=cache)
    return cache


def fresh_worktree(inst: dict, cond: str) -> Path:
    """Copy the cached base checkout to a clean per-condition run dir."""
    base = ensure_base_checkout(inst)
    dst = RUNS / cond / inst["instance_id"]
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base, dst)
    return dst


# --------------------------------------------------------------------------- #
# proxy management
# --------------------------------------------------------------------------- #
def start_proxies() -> dict[str, subprocess.Popen]:
    procs: dict[str, subprocess.Popen] = {}
    for cond, cfg in PROXIES.items():
        log = RUNS / f"proxy_{cond}_events.jsonl"
        if log.exists():
            log.unlink()
        env = dict(os.environ)
        env.update({
            "IMGCTX_PORT": str(cfg["port"]),
            "IMGCTX_ENABLED": cfg["enabled"],
            "IMGCTX_LOG_PATH": str(log),
            # Full raw request/response capture per arm, so token/cost/cache and the
            # imaged bytes can be regenerated without a paid rerun (capture gap fix).
            "IMGCTX_CAPTURE_DIR": str(RUNS / f"capture_{cond}"),
        })
        env.update(cfg.get("env", {}))
        out = open(RUNS / f"proxy_{cond}.log", "w")
        procs[cond] = subprocess.Popen(
            [sys.executable, "-m", "imgctx", "serve"], env=env, cwd=str(ROOT),
            stdout=out, stderr=subprocess.STDOUT)
    # wait for health
    for _ in range(30):
        ok = True
        for cfg in PROXIES.values():
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cfg['port']}/", timeout=2)
            except urllib.error.HTTPError:
                pass  # 404 = alive
            except Exception:
                ok = False
        if ok:
            break
        time.sleep(1)
    return procs


def stop_proxies(procs: dict[str, subprocess.Popen]) -> None:
    for p in procs.values():
        p.terminate()
    for p in procs.values():
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()


# --------------------------------------------------------------------------- #
# one agent run
# --------------------------------------------------------------------------- #
CLEAR_ENV = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "LLM_API_KEY",
             "LLM_BASE_URL", "LLM_MODEL"]


def run_agent(inst: dict, cond: str, model: str, timeout: int) -> dict:
    repo_dir = fresh_worktree(inst, cond)
    port = PROXIES[cond]["port"]
    prompt = PROMPT_TEMPLATE.format(repo=inst["repo"], problem=inst["problem_statement"])

    env = {k: v for k, v in os.environ.items() if k not in CLEAR_ENV}
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"

    traj_path = RUNS / cond / f"{inst['instance_id']}.stream.jsonl"
    t0 = time.time()
    err = None
    events: list[dict] = []
    try:
        p = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--output-format", "stream-json", "--verbose",
             "--dangerously-skip-permissions"],
            cwd=repo_dir, env=env, capture_output=True, text=True, timeout=timeout)
        traj_path.write_text(p.stdout)
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
        if p.returncode != 0 and not events:
            err = f"exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}"
    except subprocess.TimeoutExpired:
        err = f"timeout>{timeout}s"

    # produced diff (source fix)
    rc, diff = _run(["git", "diff"], cwd=repo_dir, timeout=60)
    patch_path = RUNS / cond / f"{inst['instance_id']}.patch"
    patch_path.write_text(diff if rc == 0 else "")

    result_evt = next((e for e in reversed(events) if e.get("type") == "result"), None)
    usage = _sum_usage(events, result_evt)
    answer = result_evt.get("result") if result_evt else None
    is_error = bool(result_evt.get("is_error")) if result_evt else (err is not None)
    # Claude Code's OWN billed cost (real model + cache TTL). Authoritative.
    # None if the run produced no result event (crash/timeout).
    real_cost = (result_evt or {}).get("total_cost_usd")
    cost = cost_for(AGENT, usage, real_cost=real_cost)  # cost_basis=real_provider

    return {
        "instance_id": inst["instance_id"],
        "repo": inst["repo"],
        "cond": cond,
        "duration_s": round(time.time() - t0, 1),
        "num_turns": (result_evt or {}).get("num_turns"),
        "usage": usage,
        **cost,                                         # cost_usd (real) + cost_basis
        "patch_len": len(diff) if rc == 0 else 0,
        "answer_tail": (answer or "")[-200:],
        "is_error": is_error,
        "harness_error": err,
    }


def _sum_usage(events: list[dict], result_evt: dict | None) -> dict:
    """Prefer the cumulative usage in the result event; else sum per-assistant."""
    if result_evt and isinstance(result_evt.get("usage"), dict):
        u = result_evt["usage"]
        return {
            "input_tokens": u.get("input_tokens", 0) or 0,
            "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": u.get("cache_read_input_tokens", 0) or 0,
            "output_tokens": u.get("output_tokens", 0) or 0,
        }
    agg = {"input_tokens": 0, "cache_creation_input_tokens": 0,
           "cache_read_input_tokens": 0, "output_tokens": 0}
    for e in events:
        msg = e.get("message") if isinstance(e.get("message"), dict) else None
        u = msg.get("usage") if msg else None
        if isinstance(u, dict):
            for k in agg:
                agg[k] += u.get(k, 0) or 0
    return agg


def total_input_side(u: dict) -> int:
    return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--instances", nargs="*", default=None,
                    help="explicit instance_ids to run (subset of the saved selection)")
    ap.add_argument("--tag", default="",
                    help="suffix for results/run_meta files so runs don't clobber")
    ap.add_argument("--runs-dir", default=None,
                    help="override output folder (default swebench_claude_runs), e.g. a "
                         "timestamped dir so a new run never replaces an old one")
    ap.add_argument("--port-base", type=int, default=8787,
                    help="on-arm proxy port (off-arm = base+1); override for parallel runs")
    args = ap.parse_args()

    PROXIES["on"]["port"] = args.port_base
    PROXIES["off"]["port"] = args.port_base + 1

    global RUNS, REPOS, SEL_PATH
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
        REPOS = HERE / "swebench_claude_runs" / "_repos_cache"  # share the repo cache
        SEL_PATH = RUNS / "instances.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    REPOS.mkdir(parents=True, exist_ok=True)
    meta = profile_meta(AGENT, BENCHMARK)
    meta["model"] = args.model
    (RUNS / f"run_meta{args.tag}.json").write_text(json.dumps(meta, indent=2))

    if SEL_PATH.exists() and not args.select_only:
        instances = json.loads(SEL_PATH.read_text())
    else:
        instances = select_instances(args.n)
        SEL_PATH.write_text(json.dumps(instances, indent=2))
        print(f"selected {len(instances)} instances -> {SEL_PATH}")
        for it in instances:
            print(f"  {it['instance_id']:35s} {it['repo']}")
        if args.select_only:
            return

    if args.instances:
        instances = [it for it in instances if it["instance_id"] in set(args.instances)]
    instances = instances[:args.n]

    procs = start_proxies()
    print(f"proxies up: on=8787 off=8788")
    results: list[dict] = []
    results_path = RUNS / f"results{args.tag}.json"
    try:
        for k, inst in enumerate(instances, 1):
            for cond in ("off", "on"):
                print(f"[{k}/{len(instances)}] {inst['instance_id']} {cond} ...", flush=True)
                try:
                    r = run_agent(inst, cond, args.model, args.timeout)
                except Exception as e:
                    r = {"instance_id": inst["instance_id"], "repo": inst["repo"],
                         "cond": cond, "harness_error": f"{type(e).__name__}:{e}",
                         "usage": {}, "cost_usd": None, "is_error": True}
                u = r.get("usage", {})
                print(f"    turns={r.get('num_turns')} in={total_input_side(u)} "
                      f"out={u.get('output_tokens')} cost(claude)=${r.get('cost_usd')} "
                      f"patch={r.get('patch_len')}B err={r.get('is_error')}", flush=True)
                results.append(r)
                results_path.write_text(json.dumps(results, indent=2))
    finally:
        stop_proxies(procs)

    print(f"\nDONE. results -> {results_path}")


if __name__ == "__main__":
    main()
