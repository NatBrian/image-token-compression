"""HotpotQA A/B through the real Claude Code CLI + imgctx (Anthropic path).

Same instrument as the SWE-bench harness (dual proxy, `claude -p`, Anthropic
cache-aware usage) but on a short read-a-doc-then-answer task instead of a long
agentic loop. For each HotpotQA question we write its 10 context paragraphs to a
documents.md, then run Claude Code twice, compression OFF (passthrough proxy,
port 8788) and ON (imgctx proxy, port 8787), pointing the agent at the file and
asking for a single FINAL ANSWER line. Every /v1/messages call's usage, the
stream-json trajectory, the parsed answer and its EM/F1 are recorded.

Run:
  .venv/bin/python -m bench.hotpot_claude_experiment --n 5 --model haiku
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "hotpot_claude_runs"
DATA_SRC = HERE / "hotpot_runs" / "data.json"  # reuse the already-fetched questions

# NO manual pricing. Dollars come ONLY from Claude Code's own reported total_cost_usd
# (result event). We never convert tokens to dollars with an assumed rate table, 
# that mis-prices the cache TTLs and diverges from the real Anthropic bill.

# Mirror the SWE-bench arms: ON keeps the system prompt as TEXT (already cache-read
# at 0.1x) and images the high-value regions (tools, tool_results, older text).
# Distinct ports from the SWE-bench harness (8787/8788) so the two benchmarks can
# run in parallel without a proxy collision.
PROXIES = {
    "off": {"port": 8798, "enabled": "0", "env": {}},
    "on": {"port": 8797, "enabled": "1", "env": {"IMGCTX_SYSTEM": "0"}},
}

# Optional variant tag: when set, run dirs + results file + proxy logs are suffixed
# so a fix-#1 rerun (only the read-once doc imaged, warm tool prefix left as text)
# does NOT clobber the committed baseline. Set by --tools0.
TAG = ""

PROMPT_TEMPLATE = (
    "Read the file at this absolute path: {docs}\n"
    "Using ONLY the information in that file, answer the question as briefly as "
    "possible (a name, entity, number, or yes/no). Do not edit any files.\n"
    "Question: {question}\n"
    "Reply with exactly one final line formatted: FINAL ANSWER: <answer>"
)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def fetch_hotpot(n: int) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while len(rows) < n:
        length = min(100, n - len(rows))
        u = ("https://datasets-server.huggingface.co/rows?dataset=hotpotqa/hotpot_qa"
             f"&config=distractor&split=validation&offset={offset}&length={length}")
        d = json.load(urllib.request.urlopen(u, timeout=90))
        rows += [r["row"] for r in d["rows"]]
        offset += length
    return rows[:n]


def load_questions(n: int) -> list[dict]:
    if DATA_SRC.exists():
        rows = json.loads(DATA_SRC.read_text())
        if len(rows) >= n:
            return rows[:n]
    return fetch_hotpot(n)


def build_documents(row: dict) -> str:
    ctx = row["context"]
    parts = [f"## {title}\n" + " ".join(sents).strip()
             for title, sents in zip(ctx["title"], ctx["sentences"])]
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------- #
# scoring (HotpotQA official style)
# --------------------------------------------------------------------------- #
def _normalize(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def em(pred: str, gold: str) -> int:
    return int(_normalize(pred) == _normalize(gold))


def f1(pred: str, gold: str) -> float:
    p, g = _normalize(pred).split(), _normalize(gold).split()
    if not p or not g:
        return float(p == g)
    common = sum(min(p.count(w), g.count(w)) for w in set(p) if w in g)
    if common == 0:
        return 0.0
    prec, rec = common / len(p), common / len(g)
    return 2 * prec * rec / (prec + rec)


def contains(pred: str, gold: str) -> int:
    return int(_normalize(gold) in _normalize(pred))


def parse_answer(events: list[dict]) -> str:
    """Pull the FINAL ANSWER line out of the result event's text."""
    result_evt = next((e for e in reversed(events) if e.get("type") == "result"), None)
    text = (result_evt or {}).get("result") or ""
    clean = ANSI.sub("", text)
    found = None
    for line in clean.splitlines():
        m = re.search(r"FINAL ANSWER:\s*(.+)", line)
        if m:
            found = m.group(1).strip()
    if found:
        return found.strip("`*_ ")
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    return lines[-1] if lines else ""


# --------------------------------------------------------------------------- #
# proxy management (dual, both up at once)
# --------------------------------------------------------------------------- #
def start_proxies() -> dict[str, subprocess.Popen]:
    procs: dict[str, subprocess.Popen] = {}
    for cond, cfg in PROXIES.items():
        log = RUNS / f"proxy_{cond}{TAG}_events.jsonl"
        if log.exists():
            log.unlink()
        env = dict(os.environ)
        env.update({"IMGCTX_PORT": str(cfg["port"]), "IMGCTX_ENABLED": cfg["enabled"],
                    "IMGCTX_LOG_PATH": str(log)})
        # Persist full raw request/response bytes per arm so image compression, the
        # exact upstream body, and the token/cost split are all debuggable post-hoc
        # without a paid rerun.
        env["IMGCTX_CAPTURE_DIR"] = str(RUNS / f"capture_{cond}{TAG}")
        env.update(cfg.get("env", {}))
        out = open(RUNS / f"proxy_{cond}{TAG}.log", "w")
        procs[cond] = subprocess.Popen(
            [sys.executable, "-m", "imgctx", "serve"], env=env, cwd=str(ROOT),
            stdout=out, stderr=subprocess.STDOUT)
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


def run_agent(row: dict, qid: str, cond: str, model: str, timeout: int) -> dict:
    qdir = RUNS / f"{cond}{TAG}" / qid
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    docs = qdir / "documents.md"
    docs.write_text(build_documents(row))

    port = PROXIES[cond]["port"]
    prompt = PROMPT_TEMPLATE.format(docs=str(docs.resolve()), question=row["question"])
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
    gold = row["answer"]
    is_error = bool(result_evt.get("is_error")) if result_evt else (err is not None)
    # Claude Code's OWN billed cost (prices the exact model + the cache TTL it uses).
    # Ground truth. None if the run produced no result event (crash/timeout).
    real_cost = (result_evt or {}).get("total_cost_usd")

    return {
        "cond": cond, "qid": qid, "question": row["question"],
        "gold": gold, "pred": pred,
        "em": em(pred, gold), "f1": round(f1(pred, gold), 3),
        "contains": contains(pred, gold),
        "duration_s": round(time.time() - t0, 1),
        "num_turns": (result_evt or {}).get("num_turns"),
        "usage": usage,                   # real per-field token counts from Claude
        "cost_usd": real_cost,            # Claude-reported total_cost_usd, authoritative
        "doc_chars": len(docs.read_text()),
        "is_error": is_error, "harness_error": err,
    }


def _sum_usage(events: list[dict], result_evt: dict | None) -> dict:
    if result_evt and isinstance(result_evt.get("usage"), dict):
        u = result_evt["usage"]
        return {k: u.get(k, 0) or 0 for k in
                ("input_tokens", "cache_creation_input_tokens",
                 "cache_read_input_tokens", "output_tokens")}
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
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--tools0", action="store_true",
                    help="Fix #1: also set IMGCTX_TOOLS=0 so ON images ONLY the "
                         "read-once doc, leaving the reusable tool prefix as text. "
                         "Writes to *_tools0 dirs + results_tools0.json so the "
                         "committed baseline stays intact.")
    ap.add_argument("--runs-dir", default=None,
                    help="override the output folder name (default hotpot_claude_runs), "
                         "so a verification run never clobbers a committed baseline")
    args = ap.parse_args()

    global TAG, RUNS
    if args.runs_dir:
        RUNS = HERE / args.runs_dir
    if args.tools0:
        TAG = "_tools0"
        PROXIES["on"]["env"]["IMGCTX_TOOLS"] = "0"

    RUNS.mkdir(parents=True, exist_ok=True)
    rows = load_questions(args.n)
    print(f"{len(rows)} HotpotQA questions loaded", flush=True)

    procs = start_proxies()
    print(f"proxies up: on={PROXIES['on']['port']} off={PROXIES['off']['port']}", flush=True)
    results: list[dict] = []
    try:
        for i, row in enumerate(rows):
            qid = f"q{i:02d}"
            for cond in ("off", "on"):
                print(f"[{i+1}/{len(rows)}] {qid} {cond} ...", flush=True)
                try:
                    r = run_agent(row, qid, cond, args.model, args.timeout)
                except Exception as e:
                    r = {"cond": cond, "qid": qid, "harness_error": f"{type(e).__name__}:{e}",
                         "usage": {}, "cost_usd": None, "is_error": True}
                u = r.get("usage", {})
                cc = r.get("cost_usd")
                print(f"    turns={r.get('num_turns')} in={total_input_side(u)} "
                      f"out={u.get('output_tokens')} cost(claude)=${cc} "
                      f"em={r.get('em')} f1={r.get('f1')} ct={r.get('contains')} "
                      f"pred={str(r.get('pred'))[:40]!r} err={r.get('is_error')}", flush=True)
                results.append(r)
                (RUNS / f"results{TAG}.json").write_text(json.dumps(results, indent=2))
    finally:
        stop_proxies(procs)

    print(f"\nDONE. results -> {RUNS/f'results{TAG}.json'}", flush=True)


if __name__ == "__main__":
    main()
