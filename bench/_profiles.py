"""Single source of truth for the benchmark campaign: per-agent imgctx config
profiles + verified provider rate tables + cache-class-aware cost simulation.

Every driver imports `resolve_profile(agent, benchmark, cond)` to get the exact
IMGCTX_* env for its ON/OFF arm, and `cost_for(agent, usage)` to attach a cost
with an explicit `cost_basis`. The resolved profile + rate table are logged into
each results.json so any run is reproducible and every dollar is auditable.

Grounding (see bench/BENCH_TODO.md for the full derivation):
  * Anthropic rates empirically confirmed vs 40 real paid items (5-min cache TTL,
    write=1.25x fresh, read=0.1x). cost_basis = REAL (total_cost_usd) at run time;
    this table is only for the decomposition view.
  * OpenAI gpt-5.4-mini from the official price list; NO cache-write fee.
  * mimo has no public per-token price (OpenCode Zen free tier) -> simulated at a
    representative real small-model rate so cost is a number, not $0 (user choice).

Config logic (verified in code + real cost):
  * Anthropic: cache read->write = 12.5x. Keep the STATIC prefix (system + tool
    docs) as TEXT so native caching reads it at 0.1x; imaging it only inflates the
    one-time write. Image only large FRESH non-prefix content (a doc / huge
    one-shot tool_result). History-collapse only wins when the frozen prefix is
    byte-stable across turns (longdoc doc), loses when it churns (agent loops).
  * OpenAI / mimo: no write fee -> aggressive imaging everywhere is always safe.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Verified per-1M-token rate tables (USD).                                     #
# --------------------------------------------------------------------------- #
RATES: dict[str, dict] = {
    # claude-sonnet-5. Empirically confirmed against 40 real paid items.
    # At run time claude cost is the REAL total_cost_usd; this table drives the
    # per-class decomposition only.
    "anthropic": {
        "input": 3.00,          # fresh input, 1x
        "cache_write": 3.75,    # cache creation, 5-min TTL = 1.25x
        "cache_read": 0.30,     # cache read, 0.1x
        "output": 15.00,
        "cost_basis": "real_provider",
        "source": "empirical (40 real items) + Anthropic list; 5-min TTL",
    },
    # OpenAI gpt-5.4-mini. Official list price. Automatic caching: no write fee.
    "openai": {
        "input": 0.75,
        "cache_write": 0.0,     # OpenAI caching is free to write
        "cache_read": 0.075,    # cached input, 0.1x
        "output": 4.50,
        "cost_basis": "simulated",
        "source": "OpenAI list price gpt-5.4-mini (developers.openai.com/api/docs/pricing)",
    },
    # Xiaomi MiMo-V2.5 (the model behind OpenCode Zen's mimo-v2.5-free). Run via the
    # free tier so no provider cost field exists -> simulated at Xiaomi's REAL
    # first-party list price. ¥1/¥0.02/¥2 per MTok (fresh/cache-hit/output) =
    # $0.14/$0.003/$0.28 USD. No separate cache-write price.
    "mimo": {
        "input": 0.14,
        "cache_write": 0.0,     # no cache-write/storage fee on Xiaomi's list
        "cache_read": 0.003,    # cache-hit
        "output": 0.28,
        "cost_basis": "simulated",
        "source": "Xiaomi MiMo-V2.5 first-party list (mimo.mi.com/docs/price): fresh $0.14, cache-read $0.003, output $0.28 /1M",
    },
}

# agent id -> pricing/cost family
AGENT_FAMILY: dict[str, str] = {
    "claude": "anthropic",
    "codex": "openai",
    "mimo": "mimo",
}

# --------------------------------------------------------------------------- #
# imgctx config profiles. Env names verified against imgctx/config.py.         #
#   IMGCTX_SYSTEM / IMGCTX_TOOLS / IMGCTX_TOOL_RESULTS / IMGCTX_USER_TEXT /    #
#   IMGCTX_HISTORY  (all _env_bool; "1"/"0").                                  #
# --------------------------------------------------------------------------- #

# OpenAI-family (codex, mimo): no cache-write fee -> image every region. The gate
# skips anything unprofitable, so this is strictly max token + sim-cost cut.
# (codex HotpotQA: system is the ONLY imageable region -> covered by SYSTEM=1.)
_OPENAI_AGGRESSIVE = {
    "IMGCTX_SYSTEM": "1",
    "IMGCTX_TOOLS": "1",
    "IMGCTX_TOOL_RESULTS": "1",
    "IMGCTX_USER_TEXT": "1",
    "IMGCTX_HISTORY": "1",
}

# Anthropic longdoc (NQA/Gov): keep static prefix as text; image the file-read doc
# (arrives as tool_result) + freeze it via history-collapse (byte-stable -> cache
# read). Matches the config that won -15..-29% real cost.
_ANTHROPIC_DOC = {
    "IMGCTX_SYSTEM": "0",
    "IMGCTX_TOOLS": "0",
    "IMGCTX_TOOL_RESULTS": "1",
    "IMGCTX_USER_TEXT": "1",
    "IMGCTX_HISTORY": "1",
}

# Read-once doc, but keep HISTORY as TEXT. narrativeqa loops on hard items; with
# HISTORY=1 the growing loop history is re-imaged into expensive cache-WRITES every
# turn (observed: cache-write +48%, cost +46% ON vs OFF at N=2, twice). Keeping
# history text lets the native cache read it at 0.1x so a loop can't amplify cost;
# the doc itself is still imaged via TOOL_RESULTS. gov_report does NOT loop -> it
# stays on _ANTHROPIC_DOC where HISTORY=1 is harmless.
_ANTHROPIC_DOC_NOHIST = {**_ANTHROPIC_DOC, "IMGCTX_HISTORY": "0"}

# Anthropic agent-loop (SWE-bench): kill static-prefix imaging (the +26% driver)
# and the churning history-collapse; keep only first-appearance huge tool_results.
_ANTHROPIC_LOOP = {
    "IMGCTX_SYSTEM": "0",
    "IMGCTX_TOOLS": "0",
    "IMGCTX_TOOL_RESULTS": "1",
    "IMGCTX_USER_TEXT": "0",
    "IMGCTX_HISTORY": "0",
}

# (agent, benchmark) -> ON-arm region env. None => cell is skipped (reuse old data).
# benchmark keys: "hotpot", "swebench", "narrativeqa", "gov_report".
_PROFILES: dict[tuple[str, str], dict | None] = {
    ("mimo", "hotpot"): _OPENAI_AGGRESSIVE,
    ("mimo", "swebench"): _OPENAI_AGGRESSIVE,
    ("mimo", "narrativeqa"): _OPENAI_AGGRESSIVE,
    ("mimo", "gov_report"): _OPENAI_AGGRESSIVE,

    ("codex", "hotpot"): _OPENAI_AGGRESSIVE,   # system-only lever, documented
    ("codex", "swebench"): _OPENAI_AGGRESSIVE,
    ("codex", "narrativeqa"): _OPENAI_AGGRESSIVE,
    ("codex", "gov_report"): _OPENAI_AGGRESSIVE,

    ("claude", "hotpot"): None,                # SKIP: imgctx no-op, reuse old data
    ("claude", "swebench"): _ANTHROPIC_LOOP,
    ("claude", "narrativeqa"): _ANTHROPIC_DOC_NOHIST,
    ("claude", "gov_report"): _ANTHROPIC_DOC,
}


def resolve_profile(agent: str, benchmark: str, cond: str) -> dict[str, str] | None:
    """Return the IMGCTX_* env overrides for this (agent, benchmark, arm).

    cond="off" -> master switch off (pure passthrough), regardless of agent.
    cond="on"  -> the agent's pinned region profile, or None if the cell is
                  intentionally skipped (reuse old data).
    """
    if agent not in AGENT_FAMILY:
        raise ValueError(f"unknown agent {agent!r}; expected one of {list(AGENT_FAMILY)}")
    if cond == "off":
        return {"IMGCTX_ENABLED": "0"}
    if cond != "on":
        raise ValueError(f"cond must be 'on' or 'off', got {cond!r}")
    prof = _PROFILES.get((agent, benchmark))
    if prof is None:
        return None  # skipped cell
    return {"IMGCTX_ENABLED": "1", **prof}


def profile_meta(agent: str, benchmark: str) -> dict:
    """Reproducibility block to embed in results.json."""
    fam = AGENT_FAMILY.get(agent, "?")
    return {
        "agent": agent,
        "benchmark": benchmark,
        "family": fam,
        "on_env": resolve_profile(agent, benchmark, "on"),
        "off_env": resolve_profile(agent, benchmark, "off"),
        "rate_table": RATES.get(fam),
    }


def cost_for(agent: str, usage: dict, real_cost: float | None = None) -> dict:
    """Attach a cost with explicit basis.

    Returns {"cost_usd", "cost_basis", ...}.
      * claude (anthropic): use the REAL provider figure (total_cost_usd) verbatim.
        That is what the user is billed; we do NOT recompute it. cost_basis=real_provider.
      * codex / mimo: no provider cost field exists (ChatGPT subscription / free), so
        cost is SIMULATED from the family rate table, cache-class aware, with a
        per-class breakdown to show WHY (fresh vs cache-read vs output).

    `usage` is the normalized dict: fresh/cache_read/cache_write/output tokens.
    Accepts either the Anthropic field names or the read_usage field names.
    """
    fam = AGENT_FAMILY[agent]
    r = RATES[fam]

    # Providers that report a real, billed dollar figure: trust it, don't recompute.
    if r["cost_basis"] == "real_provider":
        return {"cost_usd": real_cost, "cost_basis": "real_provider",
                "cost_source": "provider total_cost_usd"}

    # No provider cost field -> simulate from the verified rate table.
    fresh = usage.get("fresh_tokens")
    if fresh is None:
        fresh = usage.get("input_tokens", 0) or 0
    cread = usage.get("cache_read", usage.get("cached_tokens",
             usage.get("cache_read_input_tokens", 0))) or 0
    cwrite = usage.get("cache_write", usage.get("cache_write_tokens",
             usage.get("cache_creation_input_tokens", 0))) or 0
    out = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0

    sim = (fresh * r["input"] + cread * r["cache_read"]
           + cwrite * r["cache_write"] + out * r["output"]) / 1e6
    breakdown = {
        "fresh_usd": round(fresh * r["input"] / 1e6, 6),
        "cache_read_usd": round(cread * r["cache_read"] / 1e6, 6),
        "cache_write_usd": round(cwrite * r["cache_write"] / 1e6, 6),
        "output_usd": round(out * r["output"] / 1e6, 6),
        "rates_per_1m": {k: r[k] for k in ("input", "cache_write", "cache_read", "output")},
    }
    return {"cost_usd": round(sim, 6), "cost_basis": "simulated",
            "cost_source": r["source"], "cost_breakdown": breakdown}
