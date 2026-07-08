"""A/B token + correctness harness.

For each case, sends the SAME logical request to the real upstream twice:
  OFF: original text body
  ON : body after imgctx transform_request (bulky text -> images)
and reports upstream-billed prompt_tokens for each, plus a probe question whose
answer is a needle embedded in the payload (correctness parity).

Usage:
  .venv/bin/python -m bench.ab            # default cases
  IMGCTX_UPSTREAM_BASE=... .venv/bin/python -m bench.ab
"""
from __future__ import annotations

import json
import os
import time

import httpx

from imgctx.config import load_settings
from imgctx.transform import transform_request

UPSTREAM = os.environ.get("IMGCTX_UPSTREAM_BASE", "https://opencode.ai/zen/v1").rstrip("/")
MODEL = os.environ.get("IMGCTX_BENCH_MODEL", "mimo-v2.5-free")
URL = UPSTREAM + "/chat/completions"


def _dense_code(lines: int) -> str:
    out = []
    for i in range(lines):
        out.append(
            f"export function handler{i}(ctx: Ctx, opts: Opts): Result {{"
            f" const v = ctx.value * {i} + offset_{i}; return normalize(v, opts.scale{i % 7}); }}"
        )
    return "\n".join(out)


def build_cases() -> list[dict]:
    cases = []

    # 1. Dense source code (synthetic, self-contained), needle in the middle.
    code = _dense_code(300) + "\n// NEEDLE_TOKEN: build id is ZX-88213-QW\n" + _dense_code(120)
    cases.append({
        "name": "dense_code",
        "payload": code,
        "question": "What is the build id mentioned in a NEEDLE_TOKEN comment? Answer just the id.",
        "needle": "ZX-88213-QW",
    })

    # 2. Dense JSON blob.
    data = [{"id": i, "name": f"item_{i}", "value": i * 7, "tag": "alpha" if i % 2 else "beta"} for i in range(600)]
    data.insert(300, {"id": 99999, "name": "SPECIAL_ROW", "value": 314159, "tag": "needle"})
    blob = json.dumps(data, indent=2)
    cases.append({
        "name": "json_blob",
        "payload": blob,
        "question": "What is the value of the row whose name is SPECIAL_ROW? Answer just the number.",
        "needle": "314159",
    })

    # 3. Sparse prose (gate should REJECT, expect passthrough / no savings).
    prose = ("The committee reviewed the quarterly findings in detail. " * 6 + "\n") * 60
    prose += "\nThe approved budget figure for the north region was 47021 dollars.\n"
    cases.append({
        "name": "sparse_prose",
        "payload": prose,
        "question": "What was the approved budget figure for the north region? Answer just the number.",
        "needle": "47021",
    })

    return cases


def make_body(payload: str, question: str) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": f"Use the tool output below to answer.\n\nQUESTION: {question}"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": payload},
        ],
        "max_tokens": 1500,
        "stream": False,
    }


def call(body: dict) -> dict:
    r = httpx.post(URL, json=body, timeout=180)
    r.raise_for_status()
    j = r.json()
    msg = j["choices"][0]["message"]
    return {
        "prompt_tokens": j.get("usage", {}).get("prompt_tokens"),
        "completion_tokens": j.get("usage", {}).get("completion_tokens"),
        "answer": (msg.get("content") or msg.get("reasoning") or "").strip(),
    }


def main():
    settings = load_settings()
    cases = build_cases()
    rows = []
    for c in cases:
        off_body = make_body(c["payload"], c["question"])
        on_body, stats = transform_request(json.loads(json.dumps(off_body)), settings)

        print(f"\n=== {c['name']}  (payload {len(c['payload'])} chars) ===")
        print(f"transform: compressed={stats.compressed} reason={stats.reason} "
              f"images={stats.image_count} regions={stats.regions}")

        off = call(off_body)
        time.sleep(1.0)
        on = call(on_body) if stats.compressed else dict(off)

        needle = c["needle"]
        off_ok = needle.lower() in off["answer"].lower()
        on_ok = needle.lower() in on["answer"].lower()
        pt_off = off["prompt_tokens"] or 0
        pt_on = on["prompt_tokens"] or 0
        saved = pt_off - pt_on
        pct = (100 * saved / pt_off) if pt_off else 0
        rows.append({
            "case": c["name"], "compressed": stats.compressed, "images": stats.image_count,
            "prompt_off": pt_off, "prompt_on": pt_on, "saved": saved, "pct": round(pct, 1),
            "needle_off": off_ok, "needle_on": on_ok,
        })
        print(f"  OFF prompt_tokens={pt_off}  needle_found={off_ok}  ans={off['answer'][:80]!r}")
        print(f"  ON  prompt_tokens={pt_on}  needle_found={on_ok}  ans={on['answer'][:80]!r}")
        print(f"  SAVED {saved} tokens ({pct:.1f}%)")

    print("\n================ SUMMARY ================")
    print(f"{'case':18} {'imgs':>4} {'off':>7} {'on':>7} {'saved':>7} {'pct':>6} {'ndl_off':>8} {'ndl_on':>7}")
    tot_off = tot_on = 0
    for r in rows:
        tot_off += r["prompt_off"]; tot_on += r["prompt_on"]
        print(f"{r['case']:18} {r['images']:>4} {r['prompt_off']:>7} {r['prompt_on']:>7} "
              f"{r['saved']:>7} {r['pct']:>5.1f}% {str(r['needle_off']):>8} {str(r['needle_on']):>7}")
    tsav = tot_off - tot_on
    print(f"{'TOTAL':18} {'':>4} {tot_off:>7} {tot_on:>7} {tsav:>7} "
          f"{(100*tsav/tot_off if tot_off else 0):>5.1f}%")
    out = {"model": MODEL, "rows": rows, "total_off": tot_off, "total_on": tot_on}
    with open("bench/last_result.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote bench/last_result.json")


if __name__ == "__main__":
    main()
