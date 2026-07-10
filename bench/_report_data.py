"""Shared data layer for the benchmark report (private helper module).

Walks a fixed list of run folders, finds every `results*.json`, and normalizes the
several usage/cost shapes that accumulated across the project's history into one
schema. It also reconstructs each run's imgctx region config and computes real and
simulated cost. It renders NO markdown itself; bench.generate_final_report imports
these helpers and produces the one canonical FINAL_REPORT.md.

Cost policy (each run carries BOTH so the report can choose):
  * REAL:   taken verbatim when present: Anthropic rows carry Claude Code's
             `cost_usd` (real_provider); some endpoints report `usage.cost_usd`
             (real_endpoint). Never recomputed.
  * SIMULATED: always computed from tokens x a per-model list rate table, clearly
             labelled, so free/subscription runs (mimo, codex, gemini) have a dollar
             figure and paid runs can be cross-checked.

Nothing is rerun; every number is derived from the captured results files.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Folders to scan (relative to bench/). Every results*.json under these is included.
RUN_DIRS = [
    "campaign_20260710_180022",
    "campaign_dryrun_20260710_152928",
    "claude_nqa_hist0_20260710_182803",
    "mimo_refix_20260710_160813",
    "hotpot_claude_runs",
    "hotpot_opencode_runs",
    "hotpot_opencode_runs_gemini_31_flash_lite_v2",
    "hotpot_runs",
    "hotpot_verify_runs",
    "longdoc_claude_runs",
    "longdoc_opencode_runs",
    "longdoc_opencode_runs_gemini_31_flash_lite",
    "longdoc_opencode_runs_gpt_54_mini",
    "swebench_claude_runs",
    "swebench_opencode_runs",
    "swebench_opencode_runs_gemini_31_flash_lite",
]

# Per-model list rates, USD per 1M tokens: (fresh_input, cache_write, cache_read, output, source)
RATES = {
    "anthropic_sonnet": (3.00, 3.75, 0.30, 15.00, "Anthropic claude-sonnet list"),
    "anthropic_haiku":  (1.00, 1.25, 0.10,  5.00, "Anthropic claude-haiku list"),
    "openai_gpt54mini": (0.75, 0.00, 0.075, 4.50, "OpenAI gpt-5.4-mini list"),
    "openai_gpt4omini": (0.15, 0.00, 0.075, 0.60, "OpenAI gpt-4o-mini list"),
    "mimo":             (0.14, 0.00, 0.003, 0.28, "Xiaomi MiMo-V2.5 first-party list"),
    "gemini_flash_lite":(0.10, 0.00, 0.025, 0.40, "Gemini 3.1 flash-lite approx list"),
}


def classify(path: str, meta: dict | None) -> dict:
    """Infer agent / model / family / rate-key from run_meta (new runs) or the
    folder+file name (older runs). Returns a dict with those + a human label."""
    p = path.lower()
    fam = agent = model = rate = None
    if meta:
        agent = meta.get("agent"); fam = meta.get("family"); model = meta.get("model")
    # family/model by path signal (works for old runs and refines new ones)
    if "gemini" in p:
        fam, model, rate = "google", model or "gemini-3.1-flash-lite", "gemini_flash_lite"
        agent = agent or "opencode"
    elif "codex" in p:
        fam, model, rate = "openai", model or "gpt-5.4-mini", "openai_gpt54mini"
        agent = agent or "codex"
    elif "gpt_54_mini" in p or "gpt54mini" in p:
        fam, model, rate = "openai", model or "gpt-5.4-mini", "openai_gpt54mini"
        agent = agent or "opencode"
    elif "gpt4omini" in p:
        fam, model, rate = "openai", "gpt-4o-mini", "openai_gpt4omini"
        agent = agent or "opencode"
    elif "claude" in p or (fam == "anthropic"):
        fam = "anthropic"
        agent = agent or "claude"
        if "haiku" in p:
            model, rate = "claude-haiku", "anthropic_haiku"
        else:
            model, rate = model or "claude-sonnet", "anthropic_sonnet"
    elif "mimo" in p or fam == "mimo":
        fam, model, rate = "mimo", model or "mimo-v2.5-free", "mimo"
        agent = agent or "opencode"
    else:
        # opencode default path (longdoc_opencode_runs, swebench_opencode_runs, hotpot_runs)
        fam, model, rate = "mimo", model or "mimo-v2.5-free", "mimo"
        agent = agent or "opencode"
    return {"agent": agent, "family": fam, "model": model, "rate_key": rate}


def norm_tokens(row: dict) -> dict:
    """Collapse the 3 usage shapes (+ oldest flat shape) into one token schema."""
    u = row.get("usage") or {}
    if "input_tokens" in u or "cache_creation_input_tokens" in u:      # claude shape
        fresh = u.get("input_tokens", 0) or 0
        cwrite = u.get("cache_creation_input_tokens", 0) or 0
        cread = u.get("cache_read_input_tokens", 0) or 0
        out = u.get("output_tokens", 0) or 0
        calls = row.get("num_turns")
        images = None            # Anthropic usage carries no image count
        compressed = None
    elif u:                                                            # opencode/codex/gemini shape
        fresh = u.get("fresh_tokens")
        if fresh is None:
            fresh = (u.get("prompt_tokens", 0) or 0) - (u.get("cached_tokens", 0) or 0) - (u.get("cache_write_tokens", 0) or 0)
        cread = u.get("cached_tokens", 0) or 0
        cwrite = u.get("cache_write_tokens", 0) or 0
        out = u.get("completion_tokens", 0) or 0
        calls = u.get("calls")
        images = u.get("images", 0) or 0
        compressed = u.get("compressed_calls")
    else:                                                             # oldest flat shape (hotpot_runs)
        fresh = row.get("prompt_tokens", 0) or 0
        cread = cwrite = 0
        out = row.get("completion_tokens", 0) or 0
        calls = row.get("calls")
        images = row.get("images", 0) or 0
        compressed = row.get("compressed_calls")
    return {"fresh": max(fresh, 0), "cache_read": cread, "cache_write": cwrite,
            "output": out, "input_total": max(fresh, 0) + cread + cwrite,
            "calls": calls, "images": images, "compressed": compressed}


def real_cost(row: dict, fam: str) -> tuple[float | None, str | None]:
    """Real cost only when the source actually reported one."""
    u = row.get("usage") or {}
    if fam == "anthropic" and row.get("cost_usd") is not None:
        return float(row["cost_usd"]), "real_provider (Claude Code total_cost_usd)"
    if u.get("has_cost") and u.get("cost_usd") is not None:
        return float(u["cost_usd"]), "real_endpoint (usage.cost_usd)"
    if row.get("cost_basis") == "real_provider" and row.get("cost_usd") is not None:
        return float(row["cost_usd"]), "real_provider"
    return None, None


def sim_cost(t: dict, rate_key: str | None) -> float | None:
    if not rate_key or rate_key not in RATES:
        return None
    rin, rcw, rcr, rout, _ = RATES[rate_key]
    return (t["fresh"] * rin + t["cache_write"] * rcw + t["cache_read"] * rcr + t["output"] * rout) / 1e6


def cond_of(row: dict) -> str | None:
    c = row.get("cond") or row.get("condition")
    return c if c in ("off", "on") else None


def bench_of(row: dict, path: str) -> str:
    if row.get("config"):
        return row["config"]
    p = path.lower()
    for b in ("hotpot", "swebench", "narrativeqa", "gov_report"):
        if b in p:
            return b
    return "unknown"


def load_meta(results_path: Path) -> dict | None:
    suffix = results_path.stem[len("results"):]
    for cand in [results_path.parent / f"run_meta{suffix}.json",
                 *sorted(results_path.parent.glob("run_meta*.json"))]:
        if cand.exists():
            try:
                return json.loads(cand.read_text())
            except Exception:
                pass
    return None


def pct(o: float | None, n: float | None) -> str:
    if not o or o == 0 or n is None:
        return "n/a"
    return f"{100.0 * (n - o) / o:+.1f}%"


# --------------------------------------------------------------------------- #
# ON-arm imgctx region config, per run. Every benchmark used a DIFFERENT config #
# (which text regions get rendered to images), so it must be reported alongside #
# the tokens/cost or the deltas are not interpretable.                          #
#                                                                               #
# Two provenance classes:                                                       #
#   * DATA:     new runs serialize the exact env into run_meta.json             #
#                  (`on_env`); read verbatim.                                    #
#   * RECON:    older runs predate run_meta; the config lived ONLY in the        #
#                  driver, and the drivers have since changed. Each is read from #
#                  the driver AT THE COMMIT that produced that folder (not the   #
#                  current file), and pinned here with that commit for audit.    #
# imgctx defaults every region ON (imgctx/config.py: all _env_bool default True),#
# so a driver that set only IMGCTX_ENABLED ran all-regions-on.                   #
# --------------------------------------------------------------------------- #
REGION_KEYS = ["IMGCTX_SYSTEM", "IMGCTX_TOOLS", "IMGCTX_TOOL_RESULTS",
               "IMGCTX_USER_TEXT", "IMGCTX_HISTORY"]
REGION_SHORT = ["SYS", "TOOLS", "TOOL_RES", "USER", "HIST"]


def _cfg(source, **over):
    d = {k: "1" for k in REGION_KEYS}   # imgctx default: every region imaged
    d.update(over)
    d["src"] = source
    return d


# Checked in order; first substring match on the run's rel path wins. More
# specific paths (…_gemini, …_gpt_54_mini, results_tools0) precede their prefixes.
RECON = [
    ("hotpot_verify_runs/claude_sonnet",  _cfg("hotpot_claude_experiment.py@cb64fc3", IMGCTX_SYSTEM="0")),
    ("hotpot_verify_runs/codex",          _cfg("hotpot_codex_experiment.py@cb64fc3 (defaults: all on)")),
    ("hotpot_verify_runs/opencode_mimo",  _cfg("hotpot_opencode_experiment.py@cb64fc3", IMGCTX_SYSTEM="0")),
    ("hotpot_verify_runs/opencode_oauth", _cfg("hotpot_opencode_experiment.py@cb64fc3", IMGCTX_SYSTEM="0")),
    ("hotpot_claude_runs/results_tools0", _cfg("hotpot_claude_experiment.py --tools0 @92ab124", IMGCTX_SYSTEM="0", IMGCTX_TOOLS="0")),
    ("hotpot_claude_runs/results",        _cfg("hotpot_claude_experiment.py@2eb3f56", IMGCTX_SYSTEM="0")),
    ("hotpot_opencode_runs_gemini",       _cfg("hotpot_opencode_experiment.py@094debc", IMGCTX_SYSTEM="0")),
    ("hotpot_opencode_runs",              _cfg("hotpot_opencode_experiment.py@094debc", IMGCTX_SYSTEM="0")),
    ("hotpot_runs/",                      _cfg("hotpot_experiment.py@c1aa5e2 (defaults: all on)")),
    ("longdoc_claude_runs",               _cfg("longdoc_claude_experiment.py@094debc", IMGCTX_SYSTEM="0", IMGCTX_TOOLS="0")),
    ("longdoc_opencode_runs_gpt_54_mini", _cfg("longdoc_opencode_experiment.py@162ccbe", IMGCTX_SYSTEM="0", IMGCTX_TOOLS="0")),
    ("longdoc_opencode_runs_gemini",      _cfg("longdoc_opencode_experiment.py@094debc (junk: provider dropped mid-run)", IMGCTX_SYSTEM="0", IMGCTX_TOOLS="0")),
    ("longdoc_opencode_runs",             _cfg("longdoc_opencode_experiment.py@2327fd7", IMGCTX_SYSTEM="0", IMGCTX_TOOLS="0")),
    ("swebench_claude_runs",              _cfg("swebench_claude_experiment.py@094debc", IMGCTX_SYSTEM="0")),
    ("swebench_opencode_runs_gemini",     _cfg("swebench_opencode_experiment.py@094debc", IMGCTX_SYSTEM="0")),
    ("swebench_opencode_runs",            _cfg("swebench_opencode_experiment.py@2327fd7", IMGCTX_SYSTEM="0")),
]


def config_for(run) -> dict | None:
    """ON-arm region config for a run: prefer run_meta.on_env (recorded in the
    data at run time), else the reconstructed driver-at-commit map above."""
    meta = run.get("meta") or {}
    onenv = meta.get("on_env")
    if isinstance(onenv, dict) and any(k in onenv for k in REGION_KEYS):
        d = {k: str(onenv.get(k, "1")) for k in REGION_KEYS}
        d["src"] = "run_meta.on_env (recorded at run time)"
        return d
    for sub, cfg in RECON:
        if sub in run["rel"]:
            return cfg
    return None


def config_bits(cfg) -> str:
    """Compact S·T·R·U·H digit string, 1=imaged 0=text."""
    return "·".join(cfg[k] for k in REGION_KEYS) if cfg else "?"


# --------------------------------------------------------------------------- #
# Image-count backfill. claude results carry no image count (Anthropic usage has #
# no such field); bench/image_backfill.json (built by bench.backfill_images from  #
# the proxy event logs, WITHOUT touching results.json) supplies per-arm counts.   #
# codex/mimo/gemini already record `images` per item in results, used directly.   #
# --------------------------------------------------------------------------- #
SIDECAR: dict[str, dict] = {}   # loaded in main(); {events-rel-path: {calls, images}}
SHARE: dict[str, int] = {}      # ON-events key -> #runs mapping to it (claude only)


def on_events_key(run) -> str | None:
    """Path (rel to bench/) of the ON-arm proxy event log for a claude run."""
    if run["family"] != "anthropic":
        return None
    d = str(Path(run["rel"]).parent)
    tag = "_tools0" if "tools0" in run["rel"] else ""
    return f"{d}/proxy_on{tag}_events.jsonl"


def on_images(run, arms) -> tuple[int | None, int | None, str, int]:
    """(images, imaging-calls, source, share_count) for the ON arm.

    claude -> from the events-backfill sidecar. share_count>1 means >1 run wrote to
    the same per-arm log (imgctx appends), so the count is folder-level, not per-run
    (longdoc nqa+gov; hotpot base/_sonnet/_haiku). Others -> summed from results.json.
    """
    on = arms.get("on") or {}
    if run["family"] == "anthropic":
        key = on_events_key(run)
        rec = SIDECAR.get(key) if key else None
        if rec is None:
            return None, None, "uncaptured", 1
        return rec["images"], rec["calls"], "events-backfill", SHARE.get(key, 1)
    imgs = on.get("images", 0) or 0
    calls = sum(on.get("calls") or [])
    return imgs, calls, "results", 1


def avg_img_call(images, calls):
    return images / calls if calls else None


def collect():
    """Return list of run dicts, each = one (results file, benchmark) grouping."""
    runs = []
    for d in RUN_DIRS:
        for f in sorted(glob.glob(f"bench/{d}/**/results*.json", recursive=True)):
            fp = Path(f)
            try:
                data = json.loads(fp.read_text())
            except Exception:
                continue
            if not isinstance(data, list) or not data:
                continue
            meta = load_meta(fp)
            cls = classify(f, meta)
            # a file may hold >1 benchmark/config -> split
            by_bench: dict[str, list] = {}
            for row in data:
                by_bench.setdefault(bench_of(row, f), []).append(row)
            rel = f[len("bench/"):] if f.startswith("bench/") else f  # strip LEADING only
            for bench, rows in by_bench.items():
                runs.append({"path": f, "rel": rel, "meta": meta,
                             "bench": bench, "rows": rows, "mtime": os.path.getmtime(f), **cls})
    return runs


def aggregate(rows, fam, rate_key):
    arms = {}
    for row in rows:
        c = cond_of(row)
        if c is None:
            continue
        a = arms.setdefault(c, {"n": 0, "err": 0, "fresh": 0, "cache_read": 0, "cache_write": 0,
                                "output": 0, "input_total": 0, "images": 0, "calls": [],
                                "real": 0.0, "real_n": 0, "sim": 0.0, "f1": [], "em": [],
                                "contains": [], "patch": [], "dur": []})
        t = norm_tokens(row)
        a["n"] += 1
        if row.get("is_error"):
            a["err"] += 1
        for k in ("fresh", "cache_read", "cache_write", "output", "input_total"):
            a[k] += t[k]
        if t["images"]:
            a["images"] += t["images"]
        if t["calls"] is not None:
            a["calls"].append(t["calls"])
        rc, _ = real_cost(row, fam)
        if rc is not None:
            a["real"] += rc; a["real_n"] += 1
        sc = sim_cost(t, rate_key)
        if sc is not None:
            a["sim"] += sc
        for k in ("f1", "em", "contains"):
            if isinstance(row.get(k), (int, float)):
                a[k].append(row[k])
        if "produced_patch" in row:
            a["patch"].append(bool(row["produced_patch"]))
        if isinstance(row.get("duration_s"), (int, float)):
            a["dur"].append(row["duration_s"])
    return arms


def avg(xs):
    return sum(xs) / len(xs) if xs else None
