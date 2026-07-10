"""Shared OpenCode-path runner for the imgctx benchmarks (mimo-v2.5-free).

Mirrors the single-port A/B pattern of bench.hotpot_experiment, but with two
differences that keep parallel/sequential benchmark runs clean:

  * The proxy is restarted per (condition, item) with IMGCTX_ENABLED toggled, so
    OFF is pure passthrough and ON is imgctx, both logged by the same instrument to
    a per-item events.jsonl (which carries the endpoint's full usage, including
    prompt_tokens_details.cached_tokens / cache_write_tokens).
  * Instead of rewriting the user's GLOBAL ~/.config/opencode/opencode.json, each
    run points opencode at an isolated config file via the OPENCODE_CONFIG env var.
    That leaves the user's real config untouched and lets different benchmarks use
    different proxy ports without colliding.

mimo-v2.5-free is FREE, so there is no provider-billed dollar figure; the harnesses
record only real tokens (incl. cache split). Any dollar number is a SEPARATE,
clearly-labelled simulation (see bench.opencode_cost_breakdown).
"""
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = str(ROOT / ".venv" / "bin" / "python")
MODEL = "opencode/mimo-v2.5-free"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def write_config(path: Path, port: int, provider: str = "opencode",
                 api_key: str | None = None, models: dict | None = None) -> Path:
    """Isolated opencode config pointing `provider` at our proxy, with headless
    permissions so `opencode run` never blocks on a prompt. Returned via OPENCODE_CONFIG.

    provider="opencode" is the zen/mimo path. For a custom OpenAI-compatible provider
    (e.g. a chat/completions gateway) pass its api_key and, if needed, a `models` block
    (e.g. to force tool_call:true so the agent can use the Read tool)."""
    options = {"baseURL": f"http://127.0.0.1:{port}/v1"}
    if api_key:
        options["apiKey"] = api_key
    prov: dict = {"options": options}
    # A custom (non-zen) provider must declare the SDK so opencode loads it as an
    # OpenAI-compatible chat/completions provider (matches the user's global config
    # and the OAuth-relay setup); zen's built-in "opencode" provider needs no npm.
    if provider != "opencode":
        prov["npm"] = "@ai-sdk/openai-compatible"
    if models:
        prov["models"] = models
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {provider: prov},
        "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    return path


def start_proxy(enabled: bool, port: int, log_path: Path,
                extra_env: dict | None = None) -> subprocess.Popen:
    env = dict(os.environ)
    env["IMGCTX_ENABLED"] = "1" if enabled else "0"
    env["IMGCTX_PORT"] = str(port)
    env["IMGCTX_LOG_PATH"] = str(log_path)
    env["IMGCTX_LOG"] = "1"
    # Always capture raw request/response bytes next to events.jsonl. If our usage/
    # cost parsing misses a field (e.g. a paid endpoint's cost lives somewhere
    # _parse_usage doesn't check), the original bytes are still on disk -- no rerun,
    # no re-billing, ever.
    env["IMGCTX_CAPTURE_DIR"] = str(log_path.parent / "capture")
    if extra_env:
        env.update(extra_env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [VENV_PY, "-m", "imgctx", "serve", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        if port_open(port):
            return proc
        time.sleep(0.25)
    raise RuntimeError(f"proxy did not come up on {port}")


def stop_proxy(proc: subprocess.Popen, port: int) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    for _ in range(40):
        if not port_open(port):
            return
        time.sleep(0.25)


# Transient zen/opencode endpoint failures (seen under concurrent load against the
# free mimo-v2.5-free route): the stream never starts, so no work is done and the
# turn can be safely retried. "No provider available" is the zen router giving up;
# the others are generic upstream drops.
TRANSIENT = re.compile(
    r"No provider available|stream error|ProviderModelNotFound|"
    r"\b(429|500|502|503|504)\b|overloaded|rate.?limit", re.IGNORECASE)


def looks_transient(out: str) -> bool:
    """True if the run failed with a retriable endpoint error (no useful output)."""
    return bool(TRANSIENT.search(out or ""))


def run_opencode(cwd: Path, prompt: str, config_path: Path,
                 timeout: int = 300, model: str = MODEL, retries: int = 3) -> str:
    """Run one headless opencode turn against the isolated config. Returns stdout+stderr.

    Retries up to `retries` times on a TRANSIENT endpoint error (e.g. zen's
    "No provider available" under concurrent load). Because such errors mean the
    stream never started, no partial work was done and re-running the same prompt in
    the same cwd is safe. A [TIMEOUT] is NOT retried (work may be in flight)."""
    env = dict(os.environ)
    env["OPENCODE_CONFIG"] = str(config_path)
    out = ""
    for attempt in range(retries + 1):
        try:
            res = subprocess.run(
                # --print-logs/--log-level DEBUG: opencode's own session/tool-call trace
                # (permission decisions, streaming steps, session/message ids) lands in
                # stderr instead of only the shared global opencode.log, so it's captured
                # per-item in stdout.txt alongside the proxy's raw request/response capture.
                ["opencode", "run", "--model", model, "--print-logs", "--log-level", "DEBUG", prompt],
                cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
            out = (res.stdout or "") + "\n" + (res.stderr or "")
        except subprocess.TimeoutExpired as e:
            return (e.stdout or "") + "\n[TIMEOUT]"
        if not looks_transient(out) or attempt == retries:
            if attempt:
                out += f"\n[RETRIED x{attempt}]"
            return out
        time.sleep(2.0 * (attempt + 1))  # linear backoff: 2s, 4s, 6s
    return out


def is_run_error(u: dict, out: str) -> bool:
    """A run counts as failed if it made no call, timed out, or produced ZERO input
    tokens (an empty completion -- the failure mode that silently corrupted the OFF
    baseline in the campaign). We do NOT test looks_transient(out) here: run_opencode
    already retried transient errors, and a recovered run still carries the original
    error text in its log -- testing it would false-flag a healthy retried run. A
    genuinely exhausted-retry failure logs no usage, so the zero-token test catches
    it anyway."""
    return (u.get("calls", 0) == 0
            or (u.get("prompt_tokens", 0) or 0) == 0
            or "[TIMEOUT]" in out)


def parse_final_answer(stdout: str) -> str:
    clean = ANSI.sub("", stdout)
    found = None
    for line in clean.splitlines():
        m = re.search(r"FINAL ANSWER:\s*(.+)", line)
        if m:
            found = m.group(1).strip()
    if found:
        return found.strip("`*_ ")
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    return lines[-1] if lines else ""


def read_usage(log_path: Path) -> dict:
    """Sum the real per-field usage across every call in a proxy event log.

    Captures everything the endpoint returns in `usage` (prompt/completion/cache
    split, reasoning/audio/image sub-tokens, and a real provider-billed `cost` if the
    endpoint reports one, e.g. OpenRouter's `usage.cost` in USD) rather than only the
    handful of fields the mimo path happens to need. `raw` keeps the untouched
    per-call usage dicts so nothing the provider sends is silently dropped."""
    t = {"prompt_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
         "completion_tokens": 0, "total_tokens": 0,
         "reasoning_tokens": 0, "audio_tokens": 0, "image_tokens": 0,
         "cost_usd": 0.0, "has_cost": False,
         "calls": 0, "compressed_calls": 0, "images": 0, "raw": []}
    if not log_path.exists():
        return t
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t["calls"] += 1
        tr = ev.get("transform") or {}
        if tr.get("compressed"):
            t["compressed_calls"] += 1
            t["images"] += tr.get("image_count", 0) or 0
        u = ev.get("usage") or {}
        t["raw"].append(u)
        # Usage keys are shape-dependent: Chat Completions uses prompt_tokens /
        # completion_tokens / prompt_tokens_details; the OpenAI Responses API (the
        # ChatGPT-OAuth codex path) uses input_tokens / output_tokens /
        # input_tokens_details / output_tokens_details. Read both so the OAuth relay's
        # events.jsonl is summed correctly without a paid rerun.
        pd = u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}
        cd = u.get("completion_tokens_details") or u.get("output_tokens_details") or {}
        t["prompt_tokens"] += u.get("prompt_tokens") or u.get("input_tokens") or 0
        t["cached_tokens"] += pd.get("cached_tokens", 0) or 0
        t["cache_write_tokens"] += pd.get("cache_write_tokens", 0) or 0
        t["completion_tokens"] += u.get("completion_tokens") or u.get("output_tokens") or 0
        t["total_tokens"] += u.get("total_tokens", 0) or 0
        t["reasoning_tokens"] += cd.get("reasoning_tokens", 0) or 0
        t["audio_tokens"] += (pd.get("audio_tokens", 0) or 0) + (cd.get("audio_tokens", 0) or 0)
        t["image_tokens"] += cd.get("image_tokens", 0) or 0
        cost = u.get("cost")
        if cost is not None:
            t["has_cost"] = True
            t["cost_usd"] += float(cost)
    t["fresh_tokens"] = t["prompt_tokens"] - t["cached_tokens"] - t["cache_write_tokens"]
    if not t["has_cost"]:
        t["cost_usd"] = None
    return t
