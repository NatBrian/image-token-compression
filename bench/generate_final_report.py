"""FINAL report: runs GROUPED by (Benchmark × CLI agent × Model × ON-region config).

Rationale: input-token reduction is universal, but the *cost* payoff depends on two
things only: (a) the CLI/provider's cache pricing (Anthropic charges a write premium;
OpenAI/mimo write free) and (b) which regions imgctx renders to images. Grouping on
exactly those axes makes the comparison clean: within a group everything else is held
constant, so the ON-vs-OFF deltas are attributable to that (agent, model, regions) cell.

Builds on bench._report_data (classify / token-normalize / cost / config / image
backfill). It ADDS: run exclusion (curated), empty-run drop, model-name canonicalization,
item-level dedup (alias files) + event-log dedup (shared append logs), and the grouped
layout.

Never reruns anything and never modifies results.json; claude image counts come from the
tracked bench/image_backfill.json sidecar (see bench.backfill_images).

Run:  .venv/bin/python -m bench.generate_final_report [--out bench/FINAL_REPORT.md]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import bench._report_data as gfr
from bench._report_data import (
    RATES, REGION_KEYS, REGION_SHORT, aggregate, avg, bench_of, config_bits,
    config_for, cond_of, norm_tokens, on_events_key, pct, real_cost, sim_cost,
)

# Runs to DROP (matched on the same `short` label the full report uses:
# rel-path with "/results" -> "/" and ".json" stripped). User-curated.
EXCLUDE = {
    "longdoc_claude_runs/",
    "longdoc_claude_runs/_gov_report",
    "mimo_refix_20260710_160813/mimo_longdoc/_gov_report",
    "longdoc_opencode_runs/_gov_report_gpt4omini",
    "campaign_dryrun_20260710_152928/mimo_hotpot/",
    "hotpot_opencode_runs/_gpt4omini",
    "campaign_dryrun_20260710_152928/mimo_longdoc/_narrativeqa",
    "longdoc_opencode_runs/_narrativeqa_gpt4omini",
    "longdoc_opencode_runs_gpt_54_mini/_narrativeqa",
    "campaign_20260710_180022/claude_swebench/",
}

BENCH_ORDER = ["hotpot", "swebench", "narrativeqa", "gov_report"]
CLI = {"claude": "Claude Code", "codex": "Codex", "mimo": "OpenCode", "opencode": "OpenCode"}


def usd(v):
    """Money cell WITHOUT a '$' char. Some math-enabled markdown renderers pair
    `$...$` across cells (even inside backticks) and merge columns; dropping the sign
    removes the trigger entirely. Columns/headers already say 'USD'/'SIMULATED'."""
    return f"`{v:.4f}`" if isinstance(v, (int, float)) else "n/a"


# Plain-English guide prepended to the report. Grounded in the measured numbers below;
# prices written WITHOUT a '$' char (renderer-safe). Kept in the generator so a re-run
# reproduces it verbatim.
EXPLAINER = """\
# imgctx cost & token guide (the pricing mechanism)

Why imgctx always cuts tokens but sometimes RAISES the bill, and how to configure it per
provider. No prior knowledge of "cache read/write" assumed. Every claim is grounded in the
measured groups further down this report.

## 1. One-paragraph summary

imgctx renders bulky **text** context into **images** before sending to the model. Fewer
text tokens means fewer INPUT tokens. Nearly every measured run cut input tokens. But the
**bill is not the token count**; it is tokens × the *price* of each token, and images change
*which price bucket* a token falls into. On some providers that re-pricing costs more than
the tokens saved. So: **imgctx always saves tokens; it saves MONEY only when its config
matches the provider's pricing and the task shape.**

## 2. Cache 101: when "cache write" and "cache read" happen

A coding agent re-sends almost the SAME giant prompt every step (system instructions, the
tool list, files it already read, the conversation so far). Providers avoid charging full
price for that repetition with a **prompt cache**:

- **Cache WRITE:** the FIRST time a chunk of text is seen, the provider stores it. You pay
  a one-time *write* price.
- **Cache READ:** every LATER step that re-sends the *identical* chunk reuses the stored
  copy. You pay a much cheaper *read* price.
- **The catch:** the cache matches on EXACT bytes. Change one byte and it is a brand-new
  chunk (a new WRITE, not a READ).

Analogy: print a document once (write), then photocopy it cheaply many times (read). Edit
the document and you must print again.

## 3. Why imgctx can INCREASE cost while cutting tokens

An image is *different bytes* than the text it replaced, so imaging a chunk **breaks its
cache match**: text that would have been a cheap repeated **cache READ** comes back as a
fresh/**cache WRITE**. Whether that helps depends entirely on the read-vs-write price gap
for your provider (section 4).

Measured proof:
- **Claude Code · haiku · hotpot** (everything imaged): input **-29.4%**, real cost
  **+124.8%**. Tokens fell, yet the bill more than doubled, because cheap cache-reads became
  expensive cache-writes.
- **Claude Code · sonnet · hotpot**: image everything (`0·1·1·1·1`) gives real cost **+15.9%**;
  image almost nothing (`0·0·1·1·1`) gives real cost **-25.4%**. Same model, same task; only
  the regions differ, and the *sign of the bill flips*.

## 4. The root cause: two provider pricing families

Everything follows from ONE table (USD per 1,000,000 tokens; from this report's rate table):

| provider | fresh input | cache WRITE | cache READ | output |
|---|--:|--:|--:|--:|
| **Anthropic** (Claude Code) sonnet | 3.00 | **3.75** | **0.30** | 15.00 |
| Anthropic haiku | 1.00 | 1.25 | 0.10 | 5.00 |
| **OpenAI** (Codex / OpenCode-gpt) | 0.75 | **0.00** | 0.075 | 4.50 |
| **mimo** (OpenCode free tier) | 0.14 | **0.00** | 0.003 | 0.28 |
| gemini flash-lite | 0.10 | 0.00 | 0.025 | 0.40 |

Two families explain every result:

- **Write-premium family = Anthropic.** A cache WRITE (3.75) costs MORE than fresh input
  (3.00) and **12.5× a cache READ** (0.30). Re-imaging already-cached text is the single
  most expensive mistake here (that is the haiku +124.8% above).
- **Free-write family = OpenAI / mimo / gemini.** Cache WRITE is **0.00**. Breaking the
  cache costs nothing extra, so imaging to cut tokens is nearly always safe on cost.

One more lever: **output** is the priciest bucket everywhere, and on **mimo output is 93×
its cache-read** (0.28 vs 0.003). If imaging makes the model TALK MORE (longer answers, more
retries), mimo's bill can rise even when input tokens crash (section 6).

## 5. The ON Regions: what each images and its cost effect

imgctx chooses, region by region, which text becomes images. A config is written
`SYS·TOOLS·TOOL_RES·USER·HIST` (1 = imaged, 0 = left as text).

| Region | What it is | Normally cached? | Image it? |
|---|---|---|---|
| **SYS** (system) | Fixed system prompt | Yes, identical every turn, so cache READ after turn 1 | **Rarely.** Imaging a stable cached prefix turns cheap reads into writes. On Anthropic this only adds cost. Keep **0**. |
| **TOOLS** | Tool / function schemas | Yes, fixed prefix, cached | **Rarely**, same reason as SYS. Keep **0** on Anthropic. |
| **TOOL_RES** (tool results) | Outputs of tool calls: file reads, search dumps | Usually **no**, large and UNIQUE, seen once | **Yes, the sweet spot.** Big, fresh, not a repeat read, so imaging shrinks real tokens with no cache penalty. |
| **USER** (user text) | The user's message text | Depends | **Only if large** (e.g. a pasted document). Small prompts: no benefit. |
| **HIST** (history) | Prior turns re-sent each step | Yes on loops, mostly cache READ | **Avoid on loops.** History grows and is re-imaged every turn, which on Anthropic re-writes cache and on mimo inflates output. **0** for loops; **1** is fine for one-shot doc tasks. |

HIST proof, Claude Code · narrativeqa, identical except history:
- `0·0·1·1·0` (history kept as text): real cost **-29.9%**.
- `0·0·1·1·1` (history imaged): real cost only **-12.7%**.
Imaging history more than halved the saving.

## 6. Task SHAPE: read-once vs loop

- **Read-once tasks** (gov_report summary, easy narrativeqa): one big UNIQUE document read a
  single time. Imaging it shrinks the one-time cost everyone pays → **wins on every
  provider.** mimo gov_report all-regions: input **-72.9%**, cost **-62.9%**; Claude
  gov_report doc-only: real cost **-41.9%**.
- **Loop tasks** (swebench code-fix, hotpot multi-hop, hard narrativeqa): the same growing
  context is re-sent every turn and is mostly warm cache. Imaging it busts that cache (bad
  on Anthropic) and can make mimo emit more output (bad on mimo). mimo swebench all-regions:
  input **-56.5%** but cost **+7.1%**; mimo narrativeqa all-regions: input **-58.8%** but
  cost **+22.7%**. Switching mimo narrativeqa to doc-only `0·0·1·1·1` → cost **-51.2%**.

## 7. Decision guide: what to turn on

### Provider CHARGES for cache writes (Anthropic / Claude Code)
Image only big, unique, read-once content; never the cached prefix or loop history.
- Start at `0·0·1·1·0` (image TOOL_RES + USER text; history as text).
- Add HIST=1 (`0·0·1·1·1`) ONLY for single-shot document tasks (gov_report **-41.9%**).
- Never SYS=1 or TOOLS=1 here; that is the **+15.9%** (hotpot) / **+26.5%** (swebench)
  all-regions mistake.
- Expect: read-once tasks **-15% to -42%**; pure agent loops best left near OFF or
  TOOL_RES-only.

### Provider does NOT charge for cache writes (Codex, OpenCode-gpt, gemini, mimo)
Breaking cache is free, so image aggressively for the biggest token cut, with ONE mimo caveat.
- Default all regions on (`1·1·1·1·1`). Codex: **-25% to -28%** simulated cost across tasks.
- **mimo caveat:** on LOOP tasks, all-regions can raise cost via output growth (swebench
  **+7.1%**, narrativeqa **+22.7%**). Use doc-only `0·0·1·1·1` for mimo loops
  (narrativeqa **-51.2%**); keep all-regions for mimo read-once docs (gov_report **-62.9%**).

### Quick lookup
| Provider family | Read-once doc task | Agent loop task |
|---|---|---|
| Anthropic (write premium) | `0·0·1·1·1` (doc + history) | `0·0·1·0·0` / near-OFF (only fresh tool results) |
| OpenAI / gemini (free write) | `1·1·1·1·1` | `1·1·1·1·1` |
| mimo (free write, pricey output) | `1·1·1·1·1` | `0·0·1·1·1` (doc-only; avoid output blow-up) |

## 8. What to trust / caveats

- **Tokens ≠ money.** Input-token cuts are real and near-universal; make COST the decision
  metric, not tokens.
- **Real vs simulated cost.** Only Claude Code reports a real provider bill (`Δ Real Cost`).
  Codex/OpenCode run on subscription/free tiers, so their cost is SIMULATED from the section-4
  rate table (`Δ Sim Cost`), clearly labelled.
- **Small samples.** Each group is 2 to 4 items. Directions are consistent and
  mechanism-explained, but exact percentages will move with more data.
- **Two noisy cells, flagged not hidden.** `OpenCode gemini swebench` shows +90% tokens (a
  degenerate run under provider instability); `OpenCode gpt-5.4-mini gov_report` shows -44%
  tokens with **0 images** (imaging did not fire, so the change is agent-trajectory noise, not
  imgctx). Do not read these as imgctx effects.
- **Quality held.** F1 / answer-contains stayed within noise of OFF and error counts did not
  rise, in the groups that carry scores.
- **Why some claude "Avg Imgs/call" cells show `n/a`.** Claude's usage report omits how many
  images imgctx made, so we recover the count from imgctx's own image log. Older runs wrote
  that log as a single shared file per ON/OFF arm and appended to it, so when several
  different runs shared one file their image counts mixed together and cannot be separated.
  Those cells show `n/a` instead of a guess; cells with a number had exactly one run writing
  their log. codex / OpenCode always show a number (their count is stored per item).

---
"""


# Plain-language orientation for a first-time reader. Deliberately carries NO numbers or
# metrics (those live in the tables below and in EXPLAINER); this section is about what the
# benchmark is, what it found in words, what it does NOT prove, and how to run it. Kept in
# the generator so a re-run reproduces it verbatim. No em dashes (house style).
NARRATIVE = """\
# What this benchmark is, in plain words

If you are seeing this repository for the first time, read this section before the numbers.
It explains what is being measured, what the results mean, and, just as important, what they
do not mean.

## What imgctx is

imgctx is a transparent proxy that sits between a coding agent (a command-line AI assistant)
and the model provider. Large language models charge by the token, and a long text prompt is
many tokens. imgctx takes bulky pieces of that text prompt and renders them into images
before the request is sent. A picture of text is usually far cheaper in tokens than the same
text spelled out, so the request that reaches the provider is smaller. If imgctx cannot do
this safely for a request, it passes the request through unchanged, so turning it on should
never break a run.

## What this benchmark measures, and why

The goal is to answer one honest question: does turning imgctx on actually save money, or
does it only save tokens? Those are not the same thing. Tokens are the size of your request;
cost is what the provider charges to serve it, and providers price different kinds of tokens
very differently.

To find out, each test runs the exact same task twice, once with imgctx OFF and once with it
ON, and compares the token usage and the cost. Everything else is held the same. The tests
span several different situations so the answer is not accidental:

- Different task shapes. Some tasks read one big document a single time and answer (document
  question-answering and summarization). Others are agent loops that keep re-sending a
  growing context every step (multi-hop reasoning and real code-fixing).
- Different coding agents. The same idea is tried through more than one command-line agent,
  because each one packages its prompt differently.
- Different model providers. Providers fall into pricing families that treat cached text
  very differently, and that turns out to decide the whole outcome.
- Different imgctx settings. imgctx can image different regions of the prompt (the system
  instructions, the tool definitions, tool outputs, the user's text, and the prior
  conversation). Which regions you image changes the result, so the tests vary that too.

## What we found, in words

- Turning imgctx on reliably makes the request smaller. Fewer input tokens is the dependable,
  repeatable effect.
- Smaller is not always cheaper. Whether fewer tokens becomes fewer dollars depends on the
  provider's price list and on the shape of the task.
- Imaging a big piece of content that is only sent once (a document, or a fresh chunk of tool
  output) is the safe, broad win. It shrinks something you were going to pay full price for
  anyway.
- Imaging text that the provider was already serving cheaply from its cache can backfire. On
  providers that charge extra to refresh the cache, re-imaging that repeated text can cost
  more than it saves, even though the token count went down.
- A few models react to imaging by writing longer answers or taking more steps. Since output
  is the most expensive kind of token everywhere, that extra output can eat the savings.
- Answer quality held up. Where the tasks are scored, correctness with imgctx on stayed in
  the same range as with it off, and failures did not increase.

The short version: imgctx saves tokens almost everywhere, and it saves money when its
settings are matched to the provider and the task. The guide and tables below show exactly
how to make that match.

## Known limitations, stated plainly

This is engineering evidence, not a peer-reviewed study. Please read it that way.

- Small samples. Each measured cell is a handful of items, not hundreds. The direction of an
  effect is trustworthy; the exact size of a percentage is not, and would move with more data.
- Simulated versus real cost. Only one of the agents here bills a real invoice we can read.
  The others run on free or subscription tiers, so their cost is a simulation computed from
  published list prices. Those figures are clearly labelled as simulated and exist to show
  the shape of the bill, not to quote an exact charge.
- Prices drift. The rate tables reflect public list prices at the time of testing. Providers
  change prices, so re-check them before trusting a dollar figure.
- A couple of noisy runs. In one case a provider became unstable mid-run, and in another the
  imaging step did not actually fire. These are flagged in the report rather than removed, so
  you can see them and discount them yourself.
- Some image counts cannot be attributed. For part of the older Claude data, several runs
  shared one image log, so their counts got mixed together and cannot be split apart. Those
  cells honestly show "n/a" instead of a guessed number.
- Not perfectly reproducible. Real agents make slightly different choices each time they run,
  so no two runs are identical to the token. The comparison that matters is OFF versus ON
  under the same setup, not one run reproduced exactly.

## How to run it yourself

The raw measurements are stored as results files under the per-benchmark folders in `bench/`
(the bulky per-item artifacts are kept out of version control; the aggregated results are
archived in `bench_data.tar.gz`). From the repository root:

- Regenerate this report: `python -m bench.generate_final_report`
- Regenerate the charts: `python -m bench.make_final_charts`
- Rebuild the Claude image-count sidecar (optional): `python -m bench.backfill_images`

Each benchmark has its own driver script under `bench/` (their file names end in
`_experiment.py`). Every driver runs the OFF arm and the ON arm back to back and writes a
results file; the header comment in each driver documents its exact settings.

## How to read the rest of this report

1. The guide directly below explains the pricing mechanism (cache reads versus cache writes)
   and gives a per-provider recipe for which regions to image.
2. The Summary groups every run by benchmark, agent, model, and imgctx region setting. Each
   delta compares ON against OFF and is only comparable to other rows with the same region
   setting.
3. The charts turn the three questions a reader usually has into pictures.
4. Detailed Runs expands every group with the full token breakdown, both cost bases, and a
   per-item table, so nothing is hidden.

---
"""


def short_of(run) -> str:
    return run["rel"].replace("/results", "/").replace(".json", "")


def norm_model(run) -> str:
    m = (run.get("model") or "").lower()
    fam = run["family"]
    if fam == "anthropic":
        return "claude-haiku" if "haiku" in m else "claude-sonnet"
    if fam == "mimo":
        return "mimo-v2.5-free"
    if "gpt-4o" in m or "gpt4o" in m:
        return "gpt-4o-mini"
    if "gpt-5.4" in m or "gpt54" in m or "5.4-mini" in m:
        return "gpt-5.4-mini"
    if "gemini" in m:
        return "gemini-3.1-flash-lite"
    return run.get("model") or "?"


def is_empty(run) -> bool:
    """True if the run has no usable signal (every item errored / zero tokens)."""
    tok = 0
    ok = 0
    for r in run["rows"]:
        if cond_of(r) is None:
            continue
        t = norm_tokens(r)
        tok += t["input_total"] + t["output"]
        if not r.get("is_error"):
            ok += 1
    return tok == 0 or ok == 0


def dedup_rows(rows):
    """Drop exact-duplicate items (alias files like results.json vs results_sonnet.json
    carry the same run). Signature = id + cond + token split."""
    seen = set()
    out = []
    for r, folder in rows:
        c = cond_of(r)
        if c is None:
            continue
        t = norm_tokens(r)
        idv = r.get("qid") or r.get("instance_id") or "?"
        sig = (idv, c, t["fresh"], t["cache_read"], t["cache_write"], t["output"])
        if sig in seen:
            continue
        seen.add(sig)
        out.append((r, folder))
    return out


def group_on_images(runs, deduped_on_rows):
    """(images, imaging-calls, clean_logs, shared_logs) for a group's ON arm.

    claude: the proxy writes ONE append-mode event log per arm, so a log shared by >1
    physical run (different model / bench / config, incl. excluded ones) mixes their
    images irrecoverably. Count a log ONLY when exactly one run wrote it (gfr.SHARE==1);
    otherwise it is unattributable and excluded (never guessed). others: per-item from
    results.json, always attributable.
    """
    fam = runs[0]["family"]
    if fam == "anthropic":
        imgs = calls = clean = shared = 0
        seen = set()
        for run in runs:
            k = on_events_key(run)
            if k in seen:
                continue
            seen.add(k)
            if gfr.SHARE.get(k, 1) == 1:
                rec = gfr.SIDECAR.get(k)
                if rec:
                    imgs += rec["images"]
                    calls += rec["calls"]
                    clean += 1
            else:
                shared += 1
        return imgs, calls, clean, shared
    imgs = calls = 0
    for r, _ in deduped_on_rows:
        t = norm_tokens(r)
        imgs += t["images"] or 0
        calls += t["calls"] or 0
    return imgs, calls, 1, 0


def render_summary_row(g) -> str:
    o, n = g["off"], g["on"]
    ro = o["real"] if o["real_n"] else None
    rn = n["real"] if n["real_n"] else None
    so, sn = o["sim"], n["sim"]
    all_o = o["input_total"] + o["output"]
    all_n = n["input_total"] + n["output"]
    a = g["img_avg"]
    acell = f"{a:.1f}" if a is not None else "n/a"
    return (f"| {g['cli']} | {g['model']} | {g['bench']} | `{g['bits']}` | "
            f"{pct(o['input_total'], n['input_total'])} | {pct(all_o, all_n)} | "
            f"{pct(so, sn)} | {pct(ro, rn)} | {acell} |")


def render_group_detail(g) -> str:
    o, n = g["off"], g["on"]
    L = [f"### {g['cli']} · {g['model']} · ON regions `{g['bits']}`"]
    src = RATES.get(g["rate_key"], (0, 0, 0, 0, "n/a"))[4] if g["rate_key"] else "n/a"
    bitmap = " · ".join(f"{s}={g['cfg'][k]}" for s, k in zip(REGION_SHORT, REGION_KEYS)) \
        if g["cfg"] else "?"
    L.append(f"regions: {bitmap} · sim-rate _{src}_ · merged from {g['nfolders']} run folder(s)")
    L.append("")
    L.append("| metric | OFF | ON | Δ |")
    L.append("|---|---:|---:|---:|")

    def r(label, key, fmt=lambda v: f"{v:,}"):
        return f"| {label} | {fmt(o[key])} | {fmt(n[key])} | {pct(o[key], n[key])} |"

    L.append(r("items", "n"))
    L.append(f"| errors | {o['err']} | {n['err']} | n/a |")
    L.append(r("input total", "input_total"))
    L.append(r("· fresh", "fresh"))
    L.append(r("· cache-read", "cache_read"))
    L.append(r("· cache-write", "cache_write"))
    L.append(r("output", "output"))
    all_o, all_n = o["input_total"] + o["output"], n["input_total"] + n["output"]
    L.append(f"| all tokens (in+out) | {all_o:,} | {all_n:,} | {pct(all_o, all_n)} |")
    ac_o, ac_n = avg(o["calls"]), avg(n["calls"])
    L.append(f"| avg calls/turns | {ac_o:.1f} | {ac_n:.1f} | {pct(ac_o, ac_n)} |"
             if ac_o and ac_n else f"| avg calls/turns | {ac_o} | {ac_n} | n/a |")
    if g["img_sum"] is None:
        L.append(f"| ON images (sum) | n/a | n/a | {g['img_note']} |")
    else:
        L.append(f"| ON images (sum) | n/a | {g['img_sum']:,} | {g['img_note']} |")
        if g["img_avg"] is not None:
            L.append(f"| ON avg img/call | n/a | {g['img_avg']:.2f} | over {g['img_calls']} imaging calls |")
    so, sn = o["sim"], n["sim"]
    L.append(f"| **cost SIMULATED** | {usd(so)} | {usd(sn)} | {pct(so, sn)} |")
    ro = o["real"] if o["real_n"] else None
    rn = n["real"] if n["real_n"] else None
    L.append(f"| **cost REAL** | {usd(ro)} | {usd(rn)} | {pct(ro, rn)} |")
    if o["patch"] or n["patch"]:
        po = f"{sum(o['patch'])}/{len(o['patch'])}" if o["patch"] else "n/a"
        pn = f"{sum(n['patch'])}/{len(n['patch'])}" if n["patch"] else "n/a"
        L.append(f"| patches produced | {po} | {pn} | n/a |")
    if o["f1"] or n["f1"]:
        fo, fn = avg(o["f1"]), avg(n["f1"])
        L.append(f"| F1 (avg) | {fo:.3f} | {fn:.3f} | {pct(fo, fn)} |"
                 if fo is not None and fn is not None else f"| F1 (avg) | {fo} | {fn} | n/a |")
    if o["contains"] or n["contains"]:
        co, cn = avg(o["contains"]), avg(n["contains"])
        L.append(f"| contains (avg) | {co:.3f} | {cn:.3f} | n/a |")
    du_o, du_n = avg(o["dur"]), avg(n["dur"])
    if du_o and du_n:
        L.append(f"| avg duration s | {du_o:.0f} | {du_n:.0f} | {pct(du_o, du_n)} |")
    L.append("")

    # per-item detail
    L.append("<details><summary>per-item detail</summary>\n")
    L.append("| run folder | item | cond | fresh | c-read | c-write | out | imgs | sim USD | real USD | score |")
    L.append("|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    fam = g["rate_key"]
    for r_, folder in g["items"]:
        c = cond_of(r_)
        t = norm_tokens(r_)
        rc, _ = real_cost(r_, g["family"])
        sc = sim_cost(t, g["rate_key"])
        idv = str(r_.get("qid") or r_.get("instance_id") or "?")[:20]
        if "produced_patch" in r_:
            score = "patch" if r_.get("produced_patch") else "no-patch"
        elif isinstance(r_.get("f1"), (int, float)):
            score = f"f1={r_['f1']:.2f}"
        else:
            score = "n/a"
        im = t["images"] if (g["family"] != "anthropic" and t["images"] is not None) else "n/a"
        L.append(f"| {folder} | {idv} | {c} | {t['fresh']:,} | {t['cache_read']:,} | "
                 f"{t['cache_write']:,} | {t['output']:,} | {im} | {usd(sc)} | {usd(rc)} | {score} |")
    L.append("\n</details>\n")
    return "\n".join(L)


def build_groups(runs):
    groups: dict[tuple, dict] = {}
    for run in runs:
        cfg = config_for(run)
        bits = config_bits(cfg)
        model = norm_model(run)
        cli = CLI.get(run["agent"], run["agent"])
        key = (run["bench"], cli, model, bits)
        g = groups.setdefault(key, {"bench": run["bench"], "cli": cli, "model": model,
                                    "bits": bits, "cfg": cfg, "family": run["family"],
                                    "rate_key": run["rate_key"], "runs": [], "rows": []})
        g["runs"].append(run)
        folder = run["rel"].rsplit("/", 1)[0] if "/" in run["rel"] else run["rel"]
        for r in run["rows"]:
            g["rows"].append((r, folder))

    out = []
    for key, g in groups.items():
        items = dedup_rows(g["rows"])
        arms = aggregate([r for r, _ in items], g["family"], g["rate_key"])
        if "off" not in arms or "on" not in arms:
            continue
        on_rows = [(r, f) for r, f in items if cond_of(r) == "on"]
        img_sum, img_calls, clean, shared = group_on_images(g["runs"], on_rows)
        if g["family"] == "anthropic":
            if clean == 0 and shared > 0:
                # every log this group used was co-written by other runs -> not separable
                img_sum, img_calls = None, 0
                logword = ("image log file was" if shared == 1
                           else f"{shared} image log files were")
                note = (f"shown as n/a because this group's {logword} shared with other runs "
                        "(different model / task / region), so the images are mixed together "
                        "and cannot be split back out; we show n/a instead of guessing")
            elif shared > 0:
                note = (f"counted from this group's own image log only; {shared} other log(s) "
                        "were shared with different runs and left out, so this is a floor")
            else:
                note = "counted from imgctx's own image log (this group was the only writer)"
        else:
            note = "counted per item from results.json"
        img_avg = (img_sum / img_calls) if (img_sum is not None and img_calls) else None
        nfolders = len({f for _, f in items})
        out.append({**g, "off": arms["off"], "on": arms["on"], "items": items,
                    "img_sum": img_sum, "img_calls": img_calls, "img_avg": img_avg,
                    "img_note": note, "nfolders": nfolders})
    out.sort(key=lambda x: (BENCH_ORDER.index(x["bench"]) if x["bench"] in BENCH_ORDER else 9,
                            x["cli"], x["model"], x["bits"]))
    return out


def prepare_groups():
    """Load + normalize everything and return (groups, dropped_excl, dropped_empty).

    Single source of truth for the report AND the chart script, so both draw from the
    identical grouped numbers. Populates gfr.SIDECAR / gfr.SHARE as a side effect.
    """
    all_runs = gfr.collect()
    # image backfill sidecar + physical share counts (over ALL runs, pre-exclusion)
    side = Path("bench/image_backfill.json")
    gfr.SIDECAR = json.loads(side.read_text()) if side.exists() else {}
    gfr.SHARE = {}
    for run in all_runs:
        k = on_events_key(run)
        if k:
            gfr.SHARE[k] = gfr.SHARE.get(k, 0) + 1

    kept, dropped_excl, dropped_empty = [], [], []
    for run in all_runs:
        if short_of(run) in EXCLUDE:
            dropped_excl.append(short_of(run))
            continue
        if is_empty(run):
            dropped_empty.append(short_of(run))
            continue
        kept.append(run)
    return build_groups(kept), dropped_excl, dropped_empty


def cost_delta(g):
    """(delta_pct, basis) for a group's ON-vs-OFF cost: REAL if the provider billed one
    (claude), else SIMULATED. Returns (None, basis) when a side is missing."""
    o, n = g["off"], g["on"]
    if o["real_n"] and n["real_n"]:
        return _pct_or_none(o["real"], n["real"]), "real"
    return _pct_or_none(o["sim"], n["sim"]), "sim"


def input_delta(g):
    return _pct_or_none(g["off"]["input_total"], g["on"]["input_total"])


def _pct_or_none(o, n):
    return None if (not o or o == 0 or n is None) else 100.0 * (n - o) / o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/FINAL_REPORT.md")
    args = ap.parse_args()

    groups, dropped_excl, dropped_empty = prepare_groups()
    n_kept = sum(len(g["runs"]) for g in groups)

    B = ["# FINAL benchmark report: grouped by Bench, CLI, Model, ON-regions\n",
         f"_{len(groups)} groups from {n_kept} runs (excluded {len(dropped_excl)} by request, "
         f"dropped {len(dropped_empty)} empty/failed). Nothing rerun; costs & tokens from captured "
         "results, claude image counts from the events backfill sidecar._\n"]
    if dropped_empty:
        B.append("**Dropped as empty/failed (no usable tokens):** "
                 + ", ".join(f"`{x}`" for x in sorted(set(dropped_empty))) + "\n")

    # Plain-language orientation first (no numbers), then the numeric mechanism guide
    B.append(NARRATIVE)
    B.append(EXPLAINER)

    # Rate tables
    B.append("# Rate tables used for SIMULATED cost (USD / 1M tokens)\n")
    B.append("| model class | fresh | cache-write | cache-read | output | source |")
    B.append("|---|--:|--:|--:|--:|---|")
    for k, (ri, cw, cr, ro, s) in RATES.items():
        B.append(f"| {k} | {ri} | {cw} | {cr} | {ro} | {s} |")
    B.append("")

    # Summary
    B.append("# Summary: grouped runs\n")
    B.append("ON Region = imgctx config as **SYS·TOOLS·TOOL_RES·USER·HIST** (1=imaged, "
             "0=kept as text). Δ = ON vs OFF. All Token = input+output. Avg Imgs/call = "
             "ON-arm images per model call. Deltas only comparable within the same ON-region "
             "string.\n\n"
             "**Why some claude rows show `n/a` for Avg Imgs/call:** Claude's own usage report "
             "does not say how many images imgctx made, so we read the count from imgctx's own "
             "image log. Each run writes that log as one file per ON/OFF arm, and older runs "
             "appended to the same file, so when several different runs (different model, "
             "task, or region setting) shared one file, their image counts got mixed together "
             "and can no longer be split back apart. Rather than guess, those rows show `n/a`. "
             "Rows with a number were the only run writing to their log, so the count is exact. "
             "codex / OpenCode rows always have a number because their image count is stored "
             "per item in the results file.\n")
    B.append("| CLI Agent | Model Name | Bench | ON Region | Δ Input Token | Δ All Token | Δ Sim Cost | Δ Real Cost | Avg Imgs/call |")
    B.append("|---|---|---|:--:|--:|--:|--:|--:|--:|")
    for g in groups:
        B.append(render_summary_row(g))
    B.append("")

    # Charts (rendered by bench.make_final_charts into bench/charts/, same grouped numbers)
    B.append("# Charts: visual summary\n")
    B.append("_Three charts, each answering one question a reader of the table above has. "
             "Generated by `python -m bench.make_final_charts` from the identical grouped "
             "numbers; regenerate after re-running this report._\n")

    B.append("### Q1: Does cutting tokens cut cost?\n")
    B.append("![Token vs cost quadrant](charts/chart1_token_vs_cost_quadrant.png)\n")
    B.append("Each dot is one (agent · model · task · regions) group. **Left of the vertical "
             "line = imaging cut input tokens** (almost everything does). But height is what you "
             "pay: dots in the **red zone cut tokens and STILL cost more** (the trap), dots in "
             "the **green zone are the real wins** (cheaper too). Red dots = Anthropic (charges "
             "for cache writes); green dots = free-write providers. Circles are read-once "
             "document tasks, triangles are multi-turn agent loops; notice the loops cluster "
             "toward the trap. Takeaway: **saving tokens is not the same as saving money.**\n")

    B.append("### Q2: Why can the bill go UP when tokens go DOWN?\n")
    B.append("![Why cost rises](charts/chart2_why_cost_rises.png)\n")
    B.append("One Anthropic example (Claude · hotpot), with the bill broken into what you "
             "actually pay for. **OFF**, most of the cost is cheap repeated **cache-READ** "
             "(green). **ON**, imaging changes the bytes so that text no longer matches the "
             "cache, and it comes back as expensive **cache-WRITE** (red). Input tokens fell 35%, "
             "yet the red slice grows enough that the **total bill rises 16%**. That is the "
             "whole mechanism, in dollars.\n")

    B.append("### Q3: So what should I turn ON?\n")
    B.append("![Region decision](charts/chart3_region_decision.png)\n")
    B.append("Same model and task each time. The **only** difference is the **ON-Regions "
             "config** (`SYS·TOOLS·TOOL_RES·USER·HIST`, 1=imaged 0=text), printed on each dot. "
             "The arrow names exactly which regions were switched off: Claude hotpot "
             "`0·1·1·1·1`→`0·0·1·1·1` (TOOLS off), Claude swebench `0·1·1·1·1`→`0·0·1·0·0` "
             "(TOOLS+USER+HIST off), mimo narrativeqa `1·1·1·1·1`→`0·0·1·1·1` (SYS+TOOLS off). "
             "Follow each arrow from the red dot (costlier) to the green dot (cheaper):\n\n"
             "- **Red = image the cached prompt** (system + tools + history). That block repeats "
             "every turn, so it is already cheap (**cache-READ**). Imaging it changes the bytes, "
             "the cache stops matching, and you re-pay the expensive **cache-WRITE**, so the "
             "bill goes UP.\n"
             "- **Green = image only the unique content** (the document / a fresh tool result). "
             "It is seen once and was never cached, so imaging it just shrinks it, and the bill goes "
             "DOWN.\n\n"
             "The rule: **image the big one-time content; leave the repeated prompt as text.** "
             "(Per-provider recipe in section 7 of the guide above.)\n")

    # Detailed
    B.append("# Detailed Runs\n")
    cur = None
    for g in groups:
        if g["bench"] != cur:
            cur = g["bench"]
            B.append(f"\n## ▶ Benchmark: {cur}\n")
        B.append(render_group_detail(g))

    Path(args.out).write_text("\n".join(B))
    print(f"wrote {args.out}  ({len(groups)} groups, {n_kept} runs kept, "
          f"{len(dropped_excl)} excluded, {len(dropped_empty)} empty)")
    if dropped_empty:
        print("  empty/failed:", sorted(set(dropped_empty)))


if __name__ == "__main__":
    main()
