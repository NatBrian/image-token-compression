"""Comprehensive cross-provider HotpotQA analysis script.

Aggregates all results + per-call proxy events into a unified report with every
metric requested: agent turns, per-call breakdowns, cache dynamics, trajectory
matching, cost-per-correct-answer, etc.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# ── experiment definitions ──────────────────────────────────────────────────

Experiment = dict
RUNS: dict[str, Experiment] = {
    "opencode/mimo": {
        "dir": HERE / "hotpot_runs",
        "results_file": "results.json",
        "label": "opencode/mimo-v2.5-free",
        "provider": "zen (mimo)",
        "cli": "opencode run",
        "on_config": "default (all regions imaged)",
        "has_proxy_events": True,
        "events_dir_template": "{cond}/{qid}",
    },
    "opencode/gpt4omini": {
        "dir": HERE / "hotpot_opencode_runs",
        "results_file": "results_gpt4omini.json",
        "label": "openai/gpt-4o-mini",
        "provider": "openai",
        "cli": "opencode run",
        "on_config": "default (all regions imaged)",
        "has_proxy_events": True,
        "events_dir_template": "{cond}/{qid}",
    },
    "claude/sonnet_baseline": {
        "dir": HERE / "hotpot_claude_runs",
        "results_file": "results.json",
        "label": "claude-sonnet-5 (baseline)",
        "provider": "anthropic",
        "cli": "claude -p",
        "on_config": "IMGCTX_SYSTEM=0",
        "has_proxy_events": False,
    },
    "claude/sonnet": {
        "dir": HERE / "hotpot_claude_runs",
        "results_file": "results_sonnet.json",
        "label": "claude-sonnet-5",
        "provider": "anthropic",
        "cli": "claude -p",
        "on_config": "IMGCTX_SYSTEM=0",
        "has_proxy_events": False,
    },
    "claude/sonnet_tools0": {
        "dir": HERE / "hotpot_claude_runs",
        "results_file": "results_tools0.json",
        "label": "claude-sonnet-5 tools0",
        "provider": "anthropic",
        "cli": "claude -p",
        "on_config": "IMGCTX_SYSTEM=0, IMGCTX_TOOLS=0",
        "has_proxy_events": False,
        "proxy_events_file": None,  # no per-item proxy events for tools0
    },
    "claude/haiku": {
        "dir": HERE / "hotpot_claude_runs",
        "results_file": "results_haiku.json",
        "label": "claude-haiku",
        "provider": "anthropic",
        "cli": "claude -p",
        "on_config": "IMGCTX_SYSTEM=0",
        "has_proxy_events": False,
        "proxy_events_file": "proxy_off_events.jsonl",
    },
}


# ── helpers ─────────────────────────────────────────────────────────────────


def load_results(exp: Experiment) -> list[dict]:
    path = exp["dir"] / exp["results_file"]
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_stream(qid: str, cond: str, exp: Experiment) -> list[dict]:
    """Load per-run stream.jsonl from claude runs."""
    stream_dir = exp["dir"] / f"{cond}" / qid
    stream_file = stream_dir / "stream.jsonl"
    events = []
    if stream_file.exists():
        for line in stream_file.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    return events


def load_proxy_events(qid: str, cond: str, exp: Experiment) -> list[dict]:
    """Load per-question proxy events (opencode runs). Shared proxy logs (claude)
    are NOT loaded here because they span all questions."""
    if not exp.get("has_proxy_events"):
        return []
    tmpl = exp["events_dir_template"].format(cond=cond, qid=qid)
    ev_file = exp["dir"] / tmpl / "events.jsonl"
    if not ev_file.exists():
        return []
    events = []
    for line in ev_file.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events


def parse_answer_from_stdout(stdout: str) -> str | None:
    clean = ANSI.sub("", stdout)
    for line in clean.splitlines():
        m = re.search(r"FINAL ANSWER:\s*(.+)", line)
        if m:
            return m.group(1).strip().strip("`*_ ")
    return None


def traj_match(off_calls: int, on_calls: int) -> bool:
    """Simple call-count match. A more sophisticated version could compare
    per-call tool names or token fingerprints."""
    return off_calls == on_calls


def cache_hit_rate(u: dict) -> float:
    """cached / (fresh + write + cached). Returns float 0-1."""
    if exp_is_anthropic(u):
        fresh = u.get("input_tokens", 0) or 0
        write = u.get("cache_creation_input_tokens", 0) or 0
        read = u.get("cache_read_input_tokens", 0) or 0
    else:
        fresh = u.get("fresh_tokens", u.get("prompt_tokens", 0) or 0)
        write = u.get("cache_write_tokens", 0) or 0
        read = u.get("cached_tokens", 0) or 0
    total = fresh + write + read
    return read / total if total else 0.0


def exp_is_anthropic(u: dict) -> bool:
    return "cache_creation_input_tokens" in u


def pct(on: float, off: float) -> float:
    return 100.0 * (on - off) / off if off else 0.0


# ── per-call event analysis ─────────────────────────────────────────────────


def analyze_events(events: list[dict]) -> dict:
    """Aggregate per-call metrics from proxy event logs."""
    calls = len(events)
    if calls == 0:
        return {}
    durations = []
    img_counts = []
    pixel_counts = []
    est_saveds = []
    prompt_toks = []
    comp_toks = []
    cached_toks = []
    write_toks = []
    reasoning_toks = []
    regions: dict[str, int] = {}
    compressed = 0
    turn_tokens: list[dict] = []

    total_cost = 0.0
    for ev in events:
        tr = ev.get("transform") or {}
        us = ev.get("usage") or {}
        dur = ev.get("duration_ms", 0) or 0
        durations.append(dur)

        is_compressed = tr.get("compressed", False)
        if is_compressed:
            compressed += 1
        img_counts.append(tr.get("image_count", 0) or 0)
        pixel_counts.append(tr.get("total_pixels", 0) or 0)
        est_saveds.append(tr.get("est_tokens_saved", 0) or 0)
        for r, c in (tr.get("regions") or {}).items():
            regions[r] = regions.get(r, 0) + c

        # Capture cost from upstream (zen gateway returns cost in usage)
        total_cost += us.get("cost", 0) or 0

        # Detect anthropic-style tokens
        at = us.get("input_tokens", 0) or 0
        acr = us.get("cache_read_input_tokens", 0) or 0
        acw = us.get("cache_creation_input_tokens", 0) or 0
        aot = us.get("output_tokens", 0) or 0
        is_anth = bool(at or acr or acw)

        if is_anth:
            prompt_toks.append(at + acr + acw)
            comp_toks.append(aot)
            cached_toks.append(acr)
            write_toks.append(acw)
            turn_tokens.append({"input": at, "cache_read": acr, "cache_write": acw, "output": aot})
        else:
            pt = us.get("prompt_tokens", 0) or 0
            ct = us.get("completion_tokens", 0) or 0
            prompt_toks.append(pt)
            comp_toks.append(ct)
            pd = us.get("prompt_tokens_details") or {}
            cached_toks.append(pd.get("cached_tokens", 0) or 0)
            write_toks.append(pd.get("cache_write_tokens", 0) or 0)
            turn_tokens.append({
                "input": pt,
                "cache_read": cached_toks[-1],
                "cache_write": write_toks[-1],
                "output": ct,
            })

        cd = us.get("completion_tokens_details") or {}
        reasoning_toks.append(cd.get("reasoning_tokens", 0) or 0)

    median_dur = sorted(durations)[len(durations) // 2] if durations else 0

    return {
        "calls": calls,
        "compressed_calls": compressed,
        "total_duration_ms": sum(durations),
        "median_call_duration_ms": median_dur,
        "min_duration_ms": min(durations) if durations else 0,
        "max_duration_ms": max(durations) if durations else 0,
        "total_prompt_tokens": sum(prompt_toks),
        "total_completion_tokens": sum(comp_toks),
        "total_cached_tokens": sum(cached_toks),
        "total_write_tokens": sum(write_toks),
        "total_reasoning_tokens": sum(reasoning_toks),
        "total_images": sum(img_counts),
        "total_pixels": sum(pixel_counts),
        "total_est_saved_tokens": sum(est_saveds),
        "regions": regions,
        "turn_tokens": turn_tokens,
        "per_call_prompt": prompt_toks,
        "per_call_completion": comp_toks,
        "per_call_cached": cached_toks,
        "per_call_duration_ms": durations,
        "per_call_images": img_counts,
        "total_cost": total_cost,
    }


# ── per-question analysis ──────────────────────────────────────────────────


def analyze_question(r: dict, exp: Experiment) -> dict:
    """Augment a results row with all derived metrics."""
    qid = r.get("qid") or r.get("qid", "?")
    cond = r.get("cond") or r.get("condition", "?")

    events = load_proxy_events(qid, cond, exp)
    ev_analysis = analyze_events(events) if events else {}

    stream = []
    if exp["provider"] == "anthropic":
        stream = load_stream(qid, cond, exp)

    # ── claude-specific: extract per-turn usage from stream events ──
    claude_turns = []
    claude_cost = None
    if stream:
        for ev in stream:
            if ev.get("type") == "assistant":
                msg = ev.get("message", {}) or {}
                u = msg.get("usage") or {}
                if u:
                    claude_turns.append({
                        "input": u.get("input_tokens", 0) or 0,
                        "cache_read": u.get("cache_read_input_tokens", 0) or 0,
                        "cache_write": u.get("cache_creation_input_tokens", 0) or 0,
                        "output": u.get("output_tokens", 0) or 0,
                        "cache_create_detail": u.get("cache_creation") or {},
                    })
            if ev.get("type") == "result":
                claude_cost = ev.get("total_cost_usd")
                # NOTE: DO NOT overwrite r["usage"] from stream.jsonl — the stream
                # file is shared across experiments (haiku/sonnet/tools0 all load
                # the same off/on/qXX/stream.jsonl), but each results_XXX.json has
                # the correct per-experiment usage. The per-turn data below is
                # used for display only, not for aggregates.

    # ── unified usage (from results row OR proxy events) ──
    u = r.get("usage") or {}
    is_anth = "cache_creation_input_tokens" in u or "input_tokens" in u
    ev = ev_analysis if ev_analysis else {}

    if is_anth:
        cache_write = u.get("cache_creation_input_tokens", 0) or 0
        cache_read = u.get("cache_read_input_tokens", 0) or 0
        fresh = u.get("input_tokens", 0) or 0
        out = u.get("output_tokens", 0) or 0
    else:
        # OpenAI/zen-style: try nested usage first, then top-level, then proxy events
        fresh = (u.get("fresh_tokens") or u.get("prompt_tokens")
                 or r.get("prompt_tokens")
                 or ev.get("total_prompt_tokens", 0)) or 0
        cache_read = (u.get("cached_tokens") or r.get("cached_tokens")
                      or ev.get("total_cached_tokens", 0)) or 0
        cache_write = (u.get("cache_write_tokens") or r.get("cache_write_tokens")
                       or ev.get("total_write_tokens", 0)) or 0
        out = (u.get("completion_tokens") or r.get("completion_tokens")
               or ev.get("total_completion_tokens", 0)) or 0

    total_in = fresh + cache_read + cache_write
    chr_val = cache_hit_rate(u)
    # cost: results row → claude stream → proxy events (zen gateway $)
    cost = r.get("cost_usd")
    if cost is None and claude_cost is not None:
        cost = claude_cost
    if cost is None and ev_analysis:
        proxy_cost = ev_analysis.get("total_cost")
        if proxy_cost and proxy_cost > 0:
            cost = proxy_cost
    dur = r.get("duration_s") or r.get("wall_s", 0) or 0

    # ── trajectory match (vs pair) ──
    # (filled during aggregation)

    return {
        "qid": qid,
        "cond": cond,
        "em": r.get("em"),
        "f1": r.get("f1"),
        "contains": r.get("contains"),
        "pred": r.get("pred"),
        "gold": r.get("gold"),
        "doc_chars": r.get("doc_chars", 0),
        "duration_s": dur,
        "num_calls": (ev_analysis.get("calls")
                      or u.get("calls")
                      or r.get("calls")
                      or r.get("num_turns")
                      or 0),
        "num_turns": r.get("num_turns"),
        "cost_usd": cost if cost is not None else claude_cost,
        "is_error": r.get("is_error", False) or (r.get("harness_error") is not None),
        "harness_error": r.get("harness_error"),
        # token breakdown
        "fresh_tokens": int(fresh),
        "cache_read_tokens": int(cache_read),
        "cache_write_tokens": int(cache_write),
        "total_input_tokens": int(fresh + cache_read + cache_write),
        "output_tokens": int(out),
        "cache_hit_rate": round(cache_read / (fresh + cache_read + cache_write), 4)
            if (fresh + cache_read + cache_write) > 0 else 0.0,
        # proxy events detail
        "per_call": ev_analysis,
        "claude_turns": claude_turns,
        "claude_cost": claude_cost,
    }


# ── pair matching ──────────────────────────────────────────────────────────


def pair_questions(results: list[dict], exp: Experiment) -> list[tuple[str, dict, dict]]:
    """Group results into (qid, off_row, on_row) pairs."""
    by_q: dict[str, dict] = {}
    for r in results:
        cond = r.get("cond") or r.get("condition", "?")
        qid = r.get("qid") or r.get("qid", "?")
        analyzed = analyze_question(r, exp)
        by_q.setdefault(qid, {})[cond] = analyzed
    pairs = []
    for qid in sorted(by_q.keys()):
        d = by_q[qid]
        if "off" in d and "on" in d:
            pairs.append((qid, d["off"], d["on"]))
    return pairs


# ── report generation ──────────────────────────────────────────────────────


def build_experiment_report(exp_name: str, exp: Experiment) -> str:
    results = load_results(exp)
    if not results:
        return f"\n## {exp_name}\n\n_no results_\n"

    pairs = pair_questions(results, exp)
    conds_in_data = set(r.get("cond") or r.get("condition", "?") for r in results)

    L = []
    L.append(f"\n## {exp_name}")
    L.append(f"")
    L.append(f"- **CLI:** `{exp['cli']}`  ")
    L.append(f"- **Model:** `{exp['label']}`  ")
    L.append(f"- **Provider:** {exp['provider']}  ")
    L.append(f"- **ON config:** {exp['on_config']}  ")
    L.append(f"- **Questions:** {len(results)} total, {len(pairs)} matched OFF/ON pairs  ")
    L.append(f"- **Conditions in data:** {', '.join(sorted(conds_in_data))}  ")
    L.append("")

    if not pairs:
        L.append("_No matched OFF/ON pairs to compare._\n")
        return "\n".join(L)

    # ── aggregate over matched pairs ──
    n = len(pairs)
    sum_off = defaultdict(float)
    sum_on = defaultdict(float)
    for qid, off, on in pairs:
        for k in ("fresh_tokens", "cache_read_tokens", "cache_write_tokens",
                  "total_input_tokens", "output_tokens", "duration_s",
                  "num_calls", "doc_chars"):
            sum_off[k] += off.get(k, 0) or 0
            sum_on[k] += on.get(k, 0) or 0
        sum_off["cost"] += off.get("cost_usd", 0) or 0
        sum_on["cost"] += on.get("cost_usd", 0) or 0
        sum_off["em"] += off.get("em", 0) or 0
        sum_on["em"] += on.get("em", 0) or 0
        sum_off["ct"] += off.get("contains", 0) or 0
        sum_on["ct"] += on.get("contains", 0) or 0

        # per-call aggregates
        po = off.get("per_call") or {}
        pn = on.get("per_call") or {}
        sum_off["total_duration_ms"] += po.get("total_duration_ms", 0) or 0
        sum_on["total_duration_ms"] += pn.get("total_duration_ms", 0) or 0
        sum_off["total_images"] += po.get("total_images", 0) or 0
        sum_on["total_images"] += pn.get("total_images", 0) or 0
        sum_off["total_pixels"] += po.get("total_pixels", 0) or 0
        sum_on["total_pixels"] += pn.get("total_pixels", 0) or 0
        sum_off["total_reasoning_tokens"] += po.get("total_reasoning_tokens", 0) or 0
        sum_on["total_reasoning_tokens"] += pn.get("total_reasoning_tokens", 0) or 0
        sum_off["total_est_saved_tokens"] += po.get("total_est_saved_tokens", 0) or 0
        sum_on["total_est_saved_tokens"] += pn.get("total_est_saved_tokens", 0) or 0

    # ── trajectory matching ──
    matched_traj = sum(
        1 for _, off, on in pairs if off.get("num_calls") == on.get("num_calls")
    )
    # token totals on matched-trajectory subset
    mt_off_tok = 0
    mt_on_tok = 0
    for _, off, on in pairs:
        if off.get("num_calls") == on.get("num_calls"):
            mt_off_tok += off.get("total_input_tokens", 0) or 0
            mt_on_tok += on.get("total_input_tokens", 0) or 0

    L.append("### Headline (matched pairs, n={})".format(n))
    L.append("")
    L.append("| metric | OFF | ON | Δ |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| total input tokens | {sum_off['total_input_tokens']:,.0f} | {sum_on['total_input_tokens']:,.0f} | **{pct(sum_on['total_input_tokens'], sum_off['total_input_tokens']):+.1f}%** |")
    L.append(f"| fresh (1x) | {sum_off['fresh_tokens']:,.0f} | {sum_on['fresh_tokens']:,.0f} | {pct(sum_on['fresh_tokens'], sum_off['fresh_tokens']):+.1f}% |")
    L.append(f"| cache read (~0.1x) | {sum_off['cache_read_tokens']:,.0f} | {sum_on['cache_read_tokens']:,.0f} | {pct(sum_on['cache_read_tokens'], sum_off['cache_read_tokens']):+.1f}% |")
    L.append(f"| cache write (~1.25-2x) | {sum_off['cache_write_tokens']:,.0f} | {sum_on['cache_write_tokens']:,.0f} | {pct(sum_on['cache_write_tokens'], sum_off['cache_write_tokens']):+.1f}% |")
    L.append(f"| output tokens | {sum_off['output_tokens']:,.0f} | {sum_on['output_tokens']:,.0f} | {pct(sum_on['output_tokens'], sum_off['output_tokens']):+.1f}% |")
    L.append(f"| reasoning tokens | {sum_off['total_reasoning_tokens']:,.0f} | {sum_on['total_reasoning_tokens']:,.0f} | {pct(sum_on['total_reasoning_tokens'], sum_off['total_reasoning_tokens']):+.1f}% |")
    if sum_off.get("cost") or sum_on.get("cost"):
        L.append(f"| **cost** | **${sum_off['cost']:.4f}** | **${sum_on['cost']:.4f}** | **{pct(sum_on['cost'], sum_off['cost']):+.1f}%** |")
    L.append(f"| est tokens saved (proxy) | — | {sum_on['total_est_saved_tokens']:,.0f} | — |")
    L.append(f"| exact match (EM) | {sum_off['em']:.0f}/{n} | {sum_on['em']:.0f}/{n} | — |")
    L.append(f"| contains gold | {sum_off['ct']:.0f}/{n} | {sum_on['ct']:.0f}/{n} | — |")
    L.append(f"| total calls | {sum_off['num_calls']:.0f} | {sum_on['num_calls']:.0f} | {pct(sum_on['num_calls'], sum_off['num_calls']):+.1f}% |")
    L.append(f"| matched-trajectory pairs | — | — | {matched_traj}/{n} |")
    if matched_traj:
        L.append(f"| matched-traj input tokens | {mt_off_tok:,.0f} | {mt_on_tok:,.0f} | **{pct(mt_on_tok, mt_off_tok):+.1f}%** |")
    L.append(f"| wall time | {sum_off['duration_s']:.0f}s | {sum_on['duration_s']:.0f}s | {pct(sum_on['duration_s'], sum_off['duration_s']):+.1f}% |")
    L.append(f"| total images | {sum_off['total_images']:.0f} | {sum_on['total_images']:.0f} | — |")
    L.append(f"| total pixels | {sum_off['total_pixels']:,.0f} | {sum_on['total_pixels']:,.0f} | — |")
    L.append("")

    # ── cost efficiency ──
    if sum_off.get("cost") or sum_on.get("cost"):
        off_cost_per_correct = f"${sum_off['cost']/sum_off['em']:.4f}" if sum_off['em'] else "n/a (0 correct)"
        on_cost_per_correct = f"${sum_on['cost']/sum_on['em']:.4f}" if sum_on['em'] else "n/a (0 correct)"
        off_ct_cost = f"${sum_off['cost']/sum_off['ct']:.4f}" if sum_off['ct'] else "n/a"
        on_ct_cost = f"${sum_on['cost']/sum_on['ct']:.4f}" if sum_on['ct'] else "n/a"
        L.append("### Cost Efficiency")
        L.append("")
        L.append("| metric | OFF | ON | Δ |")
        L.append("|---|---:|---:|---:|")
        L.append(f"| cost / correct answer | {off_cost_per_correct} | {on_cost_per_correct} | — |")
        L.append(f"| cost / contains-gold | {off_ct_cost} | {on_ct_cost} | — |")
        L.append("")

    # ── cache dynamics ──
    L.append("### Cache Dynamics")
    L.append("")
    L.append("| qid | OFF cache hit rate | ON cache hit rate | Δ |")
    L.append("|---|---:|---:|---:|")
    off_chr = [off.get("cache_hit_rate", 0) or 0 for _, off, _ in pairs]
    on_chr = [on.get("cache_hit_rate", 0) or 0 for _, _, on in pairs]
    for (qid, off, on), och, ochr in zip(pairs, off_chr, on_chr):
        L.append(f"| {qid} | {off.get('cache_hit_rate', 0)*100:.1f}% | {on.get('cache_hit_rate', 0)*100:.1f}% | {pct(on.get('cache_hit_rate', 0) or 0, off.get('cache_hit_rate', 0) or 0):+.1f}% |")
    mean_off_chr = (sum(off_chr) / len(off_chr) * 100) if off_chr else 0
    mean_on_chr = (sum(on_chr) / len(on_chr) * 100) if on_chr else 0
    L.append(f"| **mean** | **{mean_off_chr:.1f}%** | **{mean_on_chr:.1f}%** | {pct(mean_on_chr, mean_off_chr):+.1f}% |")
    L.append("")

    # ── per-question detail ──
    L.append("### Per-Question Detail")
    L.append("")
    token_fields = ["fresh_tokens", "cache_read_tokens", "cache_write_tokens", "total_input_tokens", "output_tokens"]
    header = "| qid | " + " | ".join(f"{k} OFF/ON" for k in token_fields) + " | Δ input tok | cost OFF | cost ON | Δ cost | EM O/N | CT O/N | calls O/N | turns O/N | traj match | dur O/N | images ON |"
    L.append(header)
    sep = "| --- |" + " ---: |" * len(token_fields) + " ---: | ---: | ---: | ---: | :--: | :--: | :--: | :--: | :--: | :--: | ---: |"
    L.append(sep)
    for qid, off, on in pairs:
        tok_parts = []
        for k in token_fields:
            ov = off.get(k, 0) or 0
            nv = on.get(k, 0) or 0
            tok_parts.append(f"{ov:,.0f}/{nv:,.0f}")
        delta_tok = pct(on.get("total_input_tokens", 0) or 0, off.get("total_input_tokens", 0) or 0)
        oc = f"${off.get('cost_usd', 0):.4f}" if off.get("cost_usd") is not None else "n/a"
        nc = f"${on.get('cost_usd', 0):.4f}" if on.get("cost_usd") is not None else "n/a"
        dc = f"{pct(on.get('cost_usd', 0) or 0, off.get('cost_usd', 0) or 0):+.0f}%" if (off.get('cost_usd') and on.get('cost_usd')) else "n/a"
        tm = "✓" if off.get("num_calls") == on.get("num_calls") else "✗"
        imgs = (on.get("per_call") or {}).get("total_images", 0) or 0
        turns_off = off.get("num_turns") or off.get("num_calls") or "?"
        turns_on = on.get("num_turns") or on.get("num_calls") or "?"
        L.append(
            f"| {qid} | {' | '.join(tok_parts)} | {delta_tok:+.1f}% | {oc} | {nc} | {dc} | "
            f"{off.get('em', '?')}/{on.get('em', '?')} | "
            f"{off.get('contains', '?')}/{on.get('contains', '?')} | "
            f"{off.get('num_calls', '?')}/{on.get('num_calls', '?')} | "
            f"{turns_off}/{turns_on} | {tm} | "
            f"{off.get('duration_s', 0):.0f}s/{on.get('duration_s', 0):.0f}s | {imgs} |"
        )
    L.append("")

    # ── per-call detail (first 2 questions) ──
    L.append("### Per-Call Breakdown (q00, q01)")
    L.append("")
    L.append("Shows each individual LLM call's prompt tokens, cached tokens, duration, and image count.")
    L.append("")
    for sample_q in ("q00", "q01"):
        for qid, off, on in pairs:
            if qid != sample_q:
                continue
            for label, arm in [("OFF", off), ("ON", on)]:
                pc = arm.get("per_call") or {}
                ptoks = pc.get("per_call_prompt", [])
                pcached = pc.get("per_call_cached", [])
                pdur = pc.get("per_call_duration_ms", [])
                pimg = pc.get("per_call_images", [])
                if not ptoks:
                    continue
                L.append(f"#### {qid} {label} ({len(ptoks)} calls)")
                L.append("")
                L.append("| call # | prompt tok | cached tok | fresh tok | completion tok | duration ms | images |")
                L.append("|---|---:|---:|---:|---:|---:|---:|")
                for i in range(len(ptoks)):
                    fresh = (ptoks[i] or 0) - (pcached[i] or 0)
                    comp = (pc.get("per_call_completion") or [0])[i] or 0
                    imgs = pimg[i] if i < len(pimg) else 0
                    dur = pdur[i] if i < len(pdur) else 0
                    L.append(f"| {i} | {ptoks[i]:,} | {pcached[i]:,} | {fresh:,} | {comp:,} | {dur:.0f} | {imgs} |")
                L.append("")
            # claude turns if available
            ct_off = off.get("claude_turns")
            ct_on = on.get("claude_turns")
            if ct_off or ct_on:
                for label, turns in [("OFF", ct_off), ("ON", ct_on)]:
                    if not turns:
                        continue
                    L.append(f"#### {qid} {label} Claude per-turn usage")
                    L.append("")
                    L.append("| turn | input tok | cache_write | cache_read | output tok |")
                    L.append("|---|---:|---:|---:|---:|")
                    for i, t in enumerate(turns):
                        L.append(f"| {i} | {t.get('input', 0):,} | {t.get('cache_write', 0):,} | {t.get('cache_read', 0):,} | {t.get('output', 0):,} |")
                    L.append("")
            break  # only first pair that matches sample_q

    # ── agent loop outliers ──
    outliers = [(qid, off, on) for qid, off, on in pairs
                if off.get("num_calls") != on.get("num_calls")]
    if outliers:
        L.append("### Agent Loop Outliers (trajectory mismatch)")
        L.append("")
        L.append("| qid | OFF calls | ON calls | OFF input tok | ON input tok | OFF dur | ON dur |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for qid, off, on in outliers:
            L.append(f"| {qid} | {off.get('num_calls', '?')} | {on.get('num_calls', '?')} | "
                     f"{off.get('total_input_tokens', 0):,} | {on.get('total_input_tokens', 0):,} | "
                     f"{off.get('duration_s', 0):.0f}s | {on.get('duration_s', 0):.0f}s |")
        L.append("")

    # ── image stats ──
    total_on_regions: dict[str, int] = {}
    for _, _, on in pairs:
        pc = on.get("per_call") or {}
        for r, c in (pc.get("regions") or {}).items():
            total_on_regions[r] = total_on_regions.get(r, 0) + c
    if total_on_regions:
        L.append("### Imaged Regions (ON arm)")
        L.append("")
        L.append("| region | count |")
        L.append("|---|---:|")
        for r in sorted(total_on_regions):
            L.append(f"| {r} | {total_on_regions[r]} |")
        L.append("")

    # ── error summary ──
    errors = [(qid, cond, r.get("harness_error") or "is_error")
              for qid, off, on in pairs for (cond, r) in [("off", off), ("on", on)]
              if r.get("is_error") or r.get("harness_error")]
    if errors:
        L.append("### Errors")
        L.append("")
        for qid, cond, err in errors:
            L.append(f"- **{qid} {cond}:** {err}")
        L.append("")

    return "\n".join(L)


# ── cross-experiment summary ──────────────────────────────────────────────


def _normalized_pair(pairs: list[tuple]) -> dict:
    """Compute per-experiment normalized metrics from matched pairs.

    'Normalized' means per-call averages (dividing by number of LLM calls),
    which isolates compression effect from agent-loop divergence.
    """
    if not pairs:
        return {}
    n = len(pairs)
    total_off_calls = sum(off.get("num_calls", 0) or 0 for _, off, _ in pairs)
    total_on_calls = sum(on.get("num_calls", 0) or 0 for _, _, on in pairs)
    return {
        "n": n,
        "off_calls": total_off_calls,
        "on_calls": total_on_calls,
        # raw totals
        "off_input": sum(off.get("total_input_tokens", 0) or 0 for _, off, _ in pairs),
        "on_input": sum(on.get("total_input_tokens", 0) or 0 for _, _, on in pairs),
        "off_fresh": sum(off.get("fresh_tokens", 0) or 0 for _, off, _ in pairs),
        "on_fresh": sum(on.get("fresh_tokens", 0) or 0 for _, _, on in pairs),
        "off_cache_read": sum(off.get("cache_read_tokens", 0) or 0 for _, off, _ in pairs),
        "on_cache_read": sum(on.get("cache_read_tokens", 0) or 0 for _, _, on in pairs),
        "off_cache_write": sum(off.get("cache_write_tokens", 0) or 0 for _, off, _ in pairs),
        "on_cache_write": sum(on.get("cache_write_tokens", 0) or 0 for _, _, on in pairs),
        "off_output": sum(off.get("output_tokens", 0) or 0 for _, off, _ in pairs),
        "on_output": sum(on.get("output_tokens", 0) or 0 for _, _, on in pairs),
        "off_cost": sum(off.get("cost_usd", 0) or 0 for _, off, _ in pairs),
        "on_cost": sum(on.get("cost_usd", 0) or 0 for _, _, on in pairs),
        "off_dur": sum(off.get("duration_s", 0) or 0 for _, off, _ in pairs),
        "on_dur": sum(on.get("duration_s", 0) or 0 for _, _, on in pairs),
        "off_em": sum(off.get("em", 0) or 0 for _, off, _ in pairs),
        "on_em": sum(on.get("em", 0) or 0 for _, _, on in pairs),
        "off_ct": sum(off.get("contains", 0) or 0 for _, off, _ in pairs),
        "on_ct": sum(on.get("contains", 0) or 0 for _, _, on in pairs),
        "matched_traj": sum(1 for _, off, on in pairs if off.get("num_calls") == on.get("num_calls")),
        # per-call normalized
        "off_input_per_call": (sum(off.get("total_input_tokens", 0) or 0 for _, off, _ in pairs)
                               / total_off_calls) if total_off_calls else 0,
        "on_input_per_call": (sum(on.get("total_input_tokens", 0) or 0 for _, _, on in pairs)
                              / total_on_calls) if total_on_calls else 0,
        "off_cost_per_call": (sum(off.get("cost_usd", 0) or 0 for _, off, _ in pairs)
                              / total_off_calls) if total_off_calls else 0,
        "on_cost_per_call": (sum(on.get("cost_usd", 0) or 0 for _, _, on in pairs)
                             / total_on_calls) if total_on_calls else 0,
    }


def build_normalized_table(all_experiments: dict[str, Experiment]) -> str:
    """Build a cross-experiment table that shows both raw totals AND
    per-call normalized numbers."""
    rows: list[tuple[str, str, dict]] = []  # (exp_name, label, normalized)
    for exp_name, exp in all_experiments.items():
        results = load_results(exp)
        pairs = pair_questions(results, exp)
        norm = _normalized_pair(pairs)
        if norm:
            rows.append((exp_name, exp["label"], norm))

    if not rows:
        return ""

    L = []
    L.append("\n## Normalized Comparison (all experiments)")
    L.append("")
    L.append("Isolates compression effect from agent-loop divergence. Two sections:")
    L.append("")
    L.append("1. **Raw totals** — summed across all questions (agent loop noise included)")
    L.append("2. **Per-call averages** — total ÷ number of LLM calls (isolates compression)")
    L.append("")

    # ── raw totals ──
    L.append("### Raw Totals (all calls summed)")
    L.append("")
    L.append("| experiment | model | matches | traj match | OFF calls | ON calls | OFF input tok | ON input tok | Δ input | OFF fresh | ON fresh | OFF cache_read | ON cache_read | OFF cache_write | ON cache_write | OFF output | ON output | OFF cost | ON cost | Δ cost | OFF EM | ON EM | OFF dur | ON dur |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for exp_name, label, norm in rows:
        L.append(
            f"| {exp_name} | `{label}` | {norm['n']} | {norm['matched_traj']}/{norm['n']} | "
            f"{norm['off_calls']} | {norm['on_calls']} | "
            f"{norm['off_input']:,} | {norm['on_input']:,} | {pct(norm['on_input'], norm['off_input']):+.1f}% | "
            f"{norm['off_fresh']:,} | {norm['on_fresh']:,} | "
            f"{norm['off_cache_read']:,} | {norm['on_cache_read']:,} | "
            f"{norm['off_cache_write']:,} | {norm['on_cache_write']:,} | "
            f"{norm['off_output']:,} | {norm['on_output']:,} | "
            + (f"${norm['off_cost']:.4f} | ${norm['on_cost']:.4f} | {pct(norm['on_cost'], norm['off_cost']):+.1f}% | " if norm['off_cost'] or norm['on_cost'] else "n/a | n/a | n/a | ")
            + f"{norm['off_em']:.0f} | {norm['on_em']:.0f} | "
            f"{norm['off_dur']:.0f}s | {norm['on_dur']:.0f}s |"
        )
    L.append("")

    # ── per-call normalized ──
    L.append("### Per-Call Normalized (averaged ÷ calls)")
    L.append("")
    L.append("This row removes the effect of differing call counts. "
             "If OFF did 3 calls and ON did 10, the **per-call** comparison shows "
             "what one call costs under each condition, independent of how many times "
             "the agent looped.")
    L.append("")
    L.append("| experiment | model | OFF calls | ON calls | OFF input/call | ON input/call | Δ per-call input | OFF \$/call | ON \$/call | Δ \$/call | OFF dur/call | ON dur/call |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for exp_name, label, norm in rows:
        dc = norm['on_calls'] - norm['off_calls']
        L.append(
            f"| {exp_name} | `{label}` | {norm['off_calls']} | {norm['on_calls']} | "
            f"{norm['off_input_per_call']:,.0f} | {norm['on_input_per_call']:,.0f} | "
            f"{pct(norm['on_input_per_call'], norm['off_input_per_call']):+.1f}% | "
            + (f"${norm['off_cost_per_call']:.4f} | ${norm['on_cost_per_call']:.4f} | {pct(norm['on_cost_per_call'], norm['off_cost_per_call']):+.1f}% | " if norm['off_cost'] or norm['on_cost'] else "n/a | n/a | n/a | ")
            + f"{norm['off_dur']/norm['off_calls']:.0f}s | {norm['on_dur']/norm['on_calls']:.0f}s |"
        )
    L.append("")

    return "\n".join(L)


def build_cross_summary(exp_reports: dict[str, str]) -> str:
    L = []
    L.append("# HotpotQA Full Cross-Provider Analysis")
    L.append("")
    L.append("Auto-generated by `bench/hotpot_full_analysis.py`")
    L.append("")
    L.append("---")
    L.append("")

    # Normalized cross-comparison table goes FIRST
    L.append(build_normalized_table(RUNS))
    L.append("---")
    L.append("")

    # quick lookup table
    L.append("## Quick Reference")
    L.append("")
    L.append("| experiment | model | provider | n questions | n matched pairs | ON config |")
    L.append("|---|---|---:|---:|---|")
    for exp_name, exp in RUNS.items():
        results = load_results(exp)
        pairs = pair_questions(results, exp)
        L.append(f"| {exp_name} | `{exp['label']}` | {exp['provider']} | {len(results)} | {len(pairs)} | {exp['on_config']} |")
    L.append("")
    L.append("---")
    L.append("")

    for exp_name, exp in RUNS.items():
        report = build_experiment_report(exp_name, exp)
        L.append(report)
        L.append("---")
        L.append("")

    return "\n".join(L)


def main():
    report = build_cross_summary({})
    out_path = HERE / "HOTPOT_FULL_COMPARISON.md"
    out_path.write_text(report)
    print(f"wrote {out_path}")
    print(f"{len(report):,} chars")


if __name__ == "__main__":
    main()
