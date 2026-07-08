"""HotpotQA end-to-end A/B experiment through the real OpenCode CLI.

For each HotpotQA (multihop) question we materialize its 10 context paragraphs
as a documents.md file, then run `opencode run` twice, once with imgctx
compression ON, once OFF, routing both through the imgctx proxy (OFF = proxy in
pure-passthrough mode) so every LLM call's token usage is logged by the same
instrument. We capture the trajectory (opencode stdout), score the answer
(EM/F1), and record per-call token usage.

Run:
  .venv/bin/python -m bench.hotpot_experiment --n 10

Outputs under bench/hotpot_runs/:
  data.json                 fetched questions
  <cond>/<qid>/documents.md context file given to opencode
  <cond>/<qid>/events.jsonl proxy event log (per-call usage + transform stats)
  <cond>/<qid>/stdout.txt   opencode trajectory
  results.json              aggregated per-question metrics (incremental)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import string
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "bench" / "hotpot_runs"
VENV_PY = str(ROOT / ".venv" / "bin" / "python")
PORT = 8799
MODEL = "opencode/mimo-v2.5-free"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---------------- data ----------------
def fetch_hotpot(n: int) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while len(rows) < n:
        length = min(100, n - len(rows))
        u = (
            "https://datasets-server.huggingface.co/rows?dataset=hotpotqa/hotpot_qa"
            f"&config=distractor&split=validation&offset={offset}&length={length}"
        )
        r = httpx.get(u, timeout=90)
        r.raise_for_status()
        for item in r.json()["rows"]:
            rows.append(item["row"])
        offset += length
    return rows[:n]


def build_documents(row: dict) -> str:
    ctx = row["context"]
    parts = []
    for title, sents in zip(ctx["title"], ctx["sentences"]):
        parts.append(f"## {title}\n" + " ".join(sents).strip())
    return "\n\n".join(parts) + "\n"


# ---------------- scoring (HotpotQA official style) ----------------
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
    common = {}
    for w in p:
        if w in g:
            common[w] = min(p.count(w), g.count(w))
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    prec = num_same / len(p)
    rec = num_same / len(g)
    return 2 * prec * rec / (prec + rec)


def contains(pred: str, gold: str) -> int:
    return int(_normalize(gold) in _normalize(pred))


# ---------------- proxy management ----------------
def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_proxy(enabled: bool, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["IMGCTX_ENABLED"] = "1" if enabled else "0"
    env["IMGCTX_LOG_PATH"] = str(log_path)
    env["IMGCTX_LOG"] = "1"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [VENV_PY, "-m", "imgctx", "serve", "--port", str(PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if _port_open(PORT):
            return proc
        time.sleep(0.25)
    raise RuntimeError("proxy did not come up")


def stop_proxy(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    for _ in range(40):
        if not _port_open(PORT):
            return
        time.sleep(0.25)


# ---------------- opencode run ----------------
def run_opencode(qdir: Path, question: str, timeout: int = 240) -> str:
    docs = str((qdir / "documents.md").resolve())
    prompt = (
        f"Read the file at this absolute path: {docs}\n"
        "Using ONLY the information in that file, answer the question as briefly "
        "as possible (a name, entity, number, or yes/no). "
        f"Question: {question}\n"
        "Reply with exactly one final line formatted: FINAL ANSWER: <answer>"
    )
    try:
        res = subprocess.run(
            ["opencode", "run", "--model", MODEL, prompt],
            cwd=str(qdir), capture_output=True, text=True, timeout=timeout,
        )
        out = res.stdout + "\n" + res.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + "\n[TIMEOUT]"
    (qdir / "stdout.txt").write_text(out)
    return out


def parse_answer(stdout: str) -> str:
    clean = ANSI.sub("", stdout)
    m = None
    for line in clean.splitlines():
        mm = re.search(r"FINAL ANSWER:\s*(.+)", line)
        if mm:
            m = mm.group(1).strip()
    if m:
        return m.strip().strip("`*_ ")
    # fallback: last non-empty content line
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    return lines[-1] if lines else ""


def summarize_events(log_path: Path) -> dict:
    calls = 0
    compressed = 0
    prompt_tokens = 0
    completion_tokens = 0
    images = 0
    regions: dict[str, int] = {}
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            calls += 1
            t = ev.get("transform") or {}
            if t.get("compressed"):
                compressed += 1
                images += t.get("image_count", 0)
                for r, c in (t.get("regions") or {}).items():
                    regions[r] = regions.get(r, 0) + c
            u = ev.get("usage") or {}
            prompt_tokens += u.get("prompt_tokens", 0) or 0
            completion_tokens += u.get("completion_tokens", 0) or 0
    return {
        "calls": calls, "compressed_calls": compressed,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "images": images, "regions": regions,
    }


# ---------------- orchestration ----------------
def set_opencode_baseurl(url: str | None):
    cfg = json.loads(OPENCODE_CONFIG.read_text()) if OPENCODE_CONFIG.exists() else {"$schema": "https://opencode.ai/config.json"}
    if url is None:
        prov = cfg.get("provider", {})
        prov.pop("opencode", None)
        if not prov:
            cfg.pop("provider", None)
        else:
            cfg["provider"] = prov
        cfg.pop("permission", None)
    else:
        cfg.setdefault("provider", {})["opencode"] = {"options": {"baseURL": url}}
        # Headless `opencode run` must not block on permission prompts.
        cfg["permission"] = {"edit": "allow", "bash": "allow", "webfetch": "allow"}
    OPENCODE_CONFIG.write_text(json.dumps(cfg, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--conditions", default="off,on")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--fresh", action="store_true", help="refetch data + wipe runs")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    data_path = RUNS / "data.json"
    if args.fresh or not data_path.exists():
        print(f"fetching {args.n} HotpotQA questions...", flush=True)
        rows = fetch_hotpot(args.n)
        data_path.write_text(json.dumps(rows, indent=2))
    else:
        rows = json.loads(data_path.read_text())[: args.n]
    print(f"{len(rows)} questions loaded", flush=True)

    backup = None
    if OPENCODE_CONFIG.exists():
        backup = OPENCODE_CONFIG.read_text()
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    results: list[dict] = []
    results_path = RUNS / "results.json"

    try:
        set_opencode_baseurl(f"http://127.0.0.1:{PORT}/v1")
        for cond in conditions:
            enabled = cond == "on"
            for i, row in enumerate(rows):
                qid = f"q{i:02d}"
                qdir = RUNS / cond / qid
                if qdir.exists():
                    shutil.rmtree(qdir)
                qdir.mkdir(parents=True)
                (qdir / "documents.md").write_text(build_documents(row))
                log_path = qdir / "events.jsonl"

                t0 = time.time()
                proc = start_proxy(enabled, log_path)
                try:
                    out = run_opencode(qdir, row["question"], timeout=args.timeout)
                finally:
                    stop_proxy(proc)
                dt = time.time() - t0

                pred = parse_answer(out)
                gold = row["answer"]
                ev = summarize_events(log_path)
                rec = {
                    "condition": cond, "qid": qid,
                    "question": row["question"], "gold": gold, "pred": pred,
                    "em": em(pred, gold), "f1": round(f1(pred, gold), 3),
                    "contains": contains(pred, gold),
                    "doc_chars": len((qdir / "documents.md").read_text()),
                    "wall_s": round(dt, 1),
                    **ev,
                }
                results.append(rec)
                results_path.write_text(json.dumps(results, indent=2))
                print(
                    f"[{cond}] {qid} calls={ev['calls']} cmp={ev['compressed_calls']} "
                    f"prompt_tok={ev['prompt_tokens']} imgs={ev['images']} "
                    f"em={rec['em']} f1={rec['f1']} ct={rec['contains']} {dt:.0f}s "
                    f"pred={pred[:40]!r} gold={gold[:30]!r}",
                    flush=True,
                )
                time.sleep(1.0)
    finally:
        if backup is not None:
            OPENCODE_CONFIG.write_text(backup)
        else:
            set_opencode_baseurl(None)
        print("restored opencode config", flush=True)

    print(f"\nDONE. results -> {results_path}", flush=True)


if __name__ == "__main__":
    main()
