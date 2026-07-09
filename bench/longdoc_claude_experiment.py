"""Long-document single-shot QA A/B through the real Claude Code CLI + imgctx.

This is the NON-cache-heavy counterpart to the SWE-bench / HotpotQA runs. Those
lost real dollars on Anthropic because the compressible mass was a *reusable*
cached prefix (Claude Code's fixed system prompt + a frozen doc re-read across
many agentic turns), which OFF already gets at the 0.1x cache-read rate; imaging
only converts those cheap reads into pricier writes.

Here we pick the opposite task shape on purpose:
  * ONE large, UNIQUE document per item (LongBench narrativeqa ~30k tok /
    gov_report ~13k tok), read exactly ONCE, answered ONCE.
  * Because the doc is unique and read once, OFF gets NO cheap re-read to lose,
    it must pay the whole doc as fresh input on the answer turn, same as ON.
  * The ON arm images ONLY the big unique payload: IMGCTX_SYSTEM=0 and
    IMGCTX_TOOLS=0 leave the fixed system+tool prefix as TEXT (so it cache-reads
    at 0.1x, identical to OFF), and only the read-once tool_result doc is imaged.
    That isolates the doc effect from the slab-cache penalty that sank the
    earlier benchmarks.

Prediction: tokens AND real dollars both fall, because the doc-token reduction
lands on fresh (1x) input that OFF cannot cache away.

Cost is Claude Code's own `total_cost_usd` (result event). NO manual pricing.

Run:
  .venv/bin/python -m bench.longdoc_claude_experiment --n 6 --config narrativeqa --model sonnet
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Reuse the exact scoring + usage/cost extraction from the HotpotQA harness so the
# instrument is identical, only the task shape and proxy config differ.
from bench.hotpot_claude_experiment import (
    em, f1, contains, parse_answer, _sum_usage, total_input_side,
    CLEAR_ENV,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "longdoc_claude_runs"

# ON images ONLY the read-once doc (tool_result/history/user_text). System+tools
# stay text so they cache-read at 0.1x exactly like OFF (no slab-cache penalty).
# Distinct ports (8799/8800) so this can run beside the other two benchmarks.
PROXIES = {
    "off": {"port": 8800, "enabled": "0", "env": {}},
    "on": {"port": 8799, "enabled": "1",
           "env": {"IMGCTX_SYSTEM": "0", "IMGCTX_TOOLS": "0"}},
}

# LongBench mirror that serves cleanly through the HF rows API.
DATASET = "bzantium/LongBench"

PROMPT_TEMPLATE = (
    "Read the ENTIRE file at this absolute path (it is long, read all of it): "
    "{docs}\n"
    "Using ONLY the information in that file, answer the question as briefly as "
    "possible (a name, entity, phrase, or short sentence). Do not edit any files.\n"
    "Question: {question}\n"
    "Reply with exactly one final line formatted: FINAL ANSWER: <answer>"
)

SUMMARY_TEMPLATE = (
    "Read the ENTIRE file at this absolute path (it is long, read all of it): "
    "{docs}\n"
    "{question}\n"
    "Write the answer as your final message. Do not edit any files.\n"
    "End with exactly one line: FINAL ANSWER: <one-sentence summary>"
)


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load_items(config: str, n: int, max_chars: int) -> list[dict]:
    """Fetch n LongBench items for `config`, capping doc length for a clean single
    read. Cache to disk so re-runs are offline + deterministic."""
    cache = RUNS / f"data_{config}.json"
    if cache.exists():
        rows = json.loads(cache.read_text())
        if len(rows) >= n:
            return [_cap(r, max_chars) for r in rows[:n]]
    rows: list[dict] = []
    offset = 0
    while len(rows) < n:
        length = min(50, n - len(rows))
        u = ("https://datasets-server.huggingface.co/rows?dataset="
             f"{DATASET}&config={config}&split=test&offset={offset}&length={length}")
        d = json.load(urllib.request.urlopen(u, timeout=120))
        batch = [r["row"] for r in d["rows"]]
        if not batch:
            break
        rows += batch
        offset += length
    RUNS.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows[:n], indent=2))
    return [_cap(r, max_chars) for r in rows[:n]]


def _cap(row: dict, max_chars: int) -> dict:
    """Trim the context so a single Read tool call ingests the whole thing; both
    arms see the identical (capped) doc, so the A/B stays fair."""
    ctx = str(row.get("context", ""))
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars] + "\n[document truncated for the benchmark]\n"
    row = dict(row)
    row["context"] = ctx
    return row


def gold_answers(row: dict) -> list[str]:
    a = row.get("answers")
    if isinstance(a, list):
        return [str(x) for x in a if str(x).strip()] or [""]
    return [str(a)] if a else [""]


def best_score(pred: str, golds: list[str]):
    e = max(em(pred, g) for g in golds)
    ff = max(f1(pred, g) for g in golds)
    c = max(contains(pred, g) for g in golds)
    return e, round(ff, 3), c


# --------------------------------------------------------------------------- #
# proxy management (dual, both up at once)  -- mirror of hotpot harness
# --------------------------------------------------------------------------- #
def start_proxies() -> dict[str, subprocess.Popen]:
    procs: dict[str, subprocess.Popen] = {}
    for cond, cfg in PROXIES.items():
        log = RUNS / f"proxy_{cond}_events.jsonl"
        if log.exists():
            log.unlink()
        env = dict(os.environ)
        env.update({"IMGCTX_PORT": str(cfg["port"]), "IMGCTX_ENABLED": cfg["enabled"],
                    "IMGCTX_LOG_PATH": str(log)})
        env.update(cfg.get("env", {}))
        out = open(RUNS / f"proxy_{cond}.log", "w")
        procs[cond] = subprocess.Popen(
            [sys.executable, "-m", "imgctx", "serve"], env=env, cwd=str(ROOT),
            stdout=out, stderr=subprocess.STDOUT)
    for _ in range(30):
        ok = True
        for cfg in PROXIES.values():
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cfg['port']}/", timeout=2)
            except urllib.error.HTTPError:
                pass
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
def run_agent(row: dict, qid: str, cond: str, config: str, model: str,
              timeout: int) -> dict:
    qdir = RUNS / cond / qid
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    docs = qdir / "document.md"
    docs.write_text(str(row["context"]))

    question = str(row.get("input", "")).strip()
    tmpl = SUMMARY_TEMPLATE if config == "gov_report" else PROMPT_TEMPLATE
    prompt = tmpl.format(docs=str(docs.resolve()), question=question)

    port = PROXIES[cond]["port"]
    env = {k: v for k, v in os.environ.items() if k not in CLEAR_ENV}
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"

    t0 = time.time()
    err = None
    events: list[dict] = []
    try:
        p = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--output-format", "stream-json", "--verbose",
             "--dangerously-skip-permissions"],
            cwd=qdir, env=env, capture_output=True, text=True, timeout=timeout)
        (qdir / "stream.jsonl").write_text(p.stdout)
        for line in p.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
        if p.returncode != 0 and not events:
            err = f"exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}"
    except subprocess.TimeoutExpired:
        err = f"timeout>{timeout}s"

    result_evt = next((e for e in reversed(events) if e.get("type") == "result"), None)
    usage = _sum_usage(events, result_evt)
    pred = parse_answer(events)
    golds = gold_answers(row)
    e, ff, c = best_score(pred, golds)
    is_error = bool(result_evt.get("is_error")) if result_evt else (err is not None)
    # Claude Code's OWN billed cost. Ground truth. None if no result event.
    real_cost = (result_evt or {}).get("total_cost_usd")

    return {
        "cond": cond, "qid": qid, "config": config,
        "question": question, "gold": golds, "pred": pred,
        "em": e, "f1": ff, "contains": c,
        "duration_s": round(time.time() - t0, 1),
        "num_turns": (result_evt or {}).get("num_turns"),
        "usage": usage,
        "cost_usd": real_cost,
        "doc_chars": len(str(row["context"])),
        "is_error": is_error, "harness_error": err,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--config", default="narrativeqa",
                    help="LongBench config: narrativeqa | gov_report | qasper | ...")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=360)
    ap.add_argument("--max-chars", type=int, default=90000,
                    help="cap doc length so a single Read ingests it all")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    rows = load_items(args.config, args.n, args.max_chars)
    print(f"{len(rows)} {args.config} items loaded "
          f"(avg doc {sum(len(str(r['context'])) for r in rows)//max(len(rows),1):,} chars)",
          flush=True)

    procs = start_proxies()
    print(f"proxies up: on={PROXIES['on']['port']} off={PROXIES['off']['port']}", flush=True)
    results: list[dict] = []
    try:
        for i, row in enumerate(rows):
            qid = f"q{i:02d}"
            for cond in ("off", "on"):
                print(f"[{i+1}/{len(rows)}] {qid} {cond} ...", flush=True)
                try:
                    r = run_agent(row, qid, cond, args.config, args.model, args.timeout)
                except Exception as ex:
                    r = {"cond": cond, "qid": qid, "config": args.config,
                         "harness_error": f"{type(ex).__name__}:{ex}",
                         "usage": {}, "cost_usd": None, "is_error": True}
                u = r.get("usage", {})
                cc = r.get("cost_usd")
                print(f"    turns={r.get('num_turns')} in={total_input_side(u)} "
                      f"out={u.get('output_tokens')} cost(claude)=${cc} "
                      f"f1={r.get('f1')} ct={r.get('contains')} "
                      f"err={r.get('is_error')}", flush=True)
                results.append(r)
                (RUNS / "results.json").write_text(json.dumps(results, indent=2))
    finally:
        stop_proxies(procs)

    print(f"\nDONE. results -> {RUNS/'results.json'}", flush=True)


if __name__ == "__main__":
    main()
