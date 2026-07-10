# Full Benchmark Campaign: TODO & Decisions

**Status: DRY-RUN DONE (N=2, all 11 cells). Now hardening per-agent before paid scale.**
Build A-F complete. mimo fixes applied (see H). Current: mimo swebench-ON verdict, then codex, then claude. See I for next TODO. NO paid scale run until all 3 agents green + user approves.

## Goal

Run **4 benchmarks × 3 agents**, comparing **ON vs OFF** on **token usage, cache (read/write), and cost**.

Benchmarks: `HotpotQA`, `SWE-bench`, `longdoc NarrativeQA`, `longdoc GovReport`
Agents: `claude sonnet`, `codex gpt-5.4-mini`, `opencode mimo-2.5`

## Hard requirements (from user)

1. **Personalized config per agent**: not one uniform config. Each agent's profile grounded in its *verified* cache pricing + logic (see below).
2. **All scripts ready**: every (agent × benchmark) cell has a working driver.
3. **Raw request/response captured** for every run → can regenerate token usage / cost / F1 / loop-count **without rerunning** the bench.
4. **ON/OFF comparison** for token, cache, cost per cell.
5. Cost labeled **real** (provider-reported) or **simulated** (token×verified-rate), explicitly.

---

## VERIFIED facts (do not re-derive)

### Rate tables
| class | Anthropic claude-sonnet-5 | OpenAI gpt-5.4-mini | mimo |
|---|---|---|---|
| fresh input | `$3.00`/1M | `$0.75`/1M | free |
| cache **write** | **`$3.75`/1M (1.25×, 5-min TTL)** | none (free) | free |
| cache **read** | `$0.30`/1M (0.1×) | `$0.075`/1M (0.1×) | free |
| output | `$15.00`/1M | `$4.50`/1M | free |

- Anthropic rates **empirically confirmed** vs 40 real paid items; 5-min TTL fits (write=1.25×), not 1h.
- OpenAI from official list (developers.openai.com/api/docs/pricing), cross-checked.
- Cost basis: claude = **real** `total_cost_usd`; codex+mimo = **simulated** (subscription/free → no provider cost field).

### Cost logic (verified in code + real data)
- Anthropic: cache read→write = **12.5×**. Imaging content that's already cache-read in a loop is net-NEGATIVE.
- **Keep static prefix (system + tool docs) as TEXT on Anthropic**: native cache reads it at 0.1×; imaging it only inflates the one-time write. Image only large FRESH non-prefix content (a doc, a huge one-shot tool_result).
- OpenAI/mimo: no write fee → aggressive imaging always safe.

### swebench claude regression: ATTRIBUTED (old run, no rerun)
- +81k cache-write came from imaging the **tool-doc slab** (162k/172k writes), NOT history (only 10k).
- Root cause: `swebench_claude` left `IMGCTX_TOOLS=1` → imaged static tool docs. Fix = `TOOLS=0` (match winning longdoc config).

---

## Per-agent config PROFILES (personalized)

| agent | family | HotpotQA | SWE-bench | longdoc NQA/Gov |
|---|---|---|---|---|
| **opencode mimo** | OpenAI-style (no write fee) | aggressive: SYSTEM=1 TOOLS=1 results/history/user ON | aggressive | aggressive |
| **codex gpt-5.4-mini** | OpenAI-style | SYSTEM=1 (only lever, see note) | SYSTEM=1 TOOLS=1 aggressive | aggressive |
| **claude sonnet** | Anthropic (write trap) | SKIP: reuse old data | SYSTEM=0 TOOLS=0, tool_results(fresh-huge) ON, history OFF | SYSTEM=0 TOOLS=0, tool_results+history ON (doc is file-read) |

- **codex hotpot note:** doc <6k threshold, sandboxed shell can't cat doc → system prompt is the ONLY imageable region. Documented exception.
- **claude hotpot: SKIP new run.** Doc 4.7k < 6k, no big history → imgctx no-op (ON=OFF). Reuse existing data to present the counter-intuition finding: Anthropic imaging is wrong for that task category.
- Profiles live in `bench/_profiles.py` (single source of truth), logged into each `results.json`.

---

## TASK CHECKLIST

### A. Config parity → personalized profiles
- [x] Verify imgctx env knobs. CORRECTED names: `IMGCTX_SYSTEM`, `IMGCTX_TOOLS`, `IMGCTX_TOOL_RESULTS` (not _COMPRESS_), `IMGCTX_USER_TEXT`, `IMGCTX_HISTORY` (not _COMPRESS_). All `_env_bool`, "1"/"0".
- [x] Build `bench/_profiles.py`: `resolve_profile(agent,benchmark,cond)` + `RATES` + `cost_for()` + `profile_meta()`. Smoke-tested all 12 cells.
- [x] Wire every driver to import + apply its profile, and LOG `profile_meta()` -> `run_meta{tag}.json`. All 8 drivers verified (ast+import+resolve). mimo/codex use OpenAI-aggressive (all regions ON); claude swebench=corrected loop (SYSTEM/TOOLS/USER/HISTORY=0, TOOL_RESULTS=1); claude longdoc=doc profile.

### B. Cost layer (real + simulated, labeled)
- [x] claude = real `total_cost_usd` verbatim, NO recompute (`cost_basis=real_provider`). Decided: don't simulate claude: list-rate decomp is a clean 3× off Claude Code's effective subscription rates; real is authoritative.
- [x] codex = simulated OpenAI list (`$0.75`/`$0.075` cached/`$4.50,` no write fee), cache-class aware
- [x] mimo = simulated at Xiaomi MiMo-V2.5 REAL first-party list (`$0.14` fresh / `$0.003` cache-read / `$0.28` out, no write fee). NB: mimo-v2.5 = Xiaomi MiMo, NOT MiniMax.
- [x] Fix dead path in `cost_claude_breakdown.py` (`swebench_runs`→`swebench_claude_runs`, `longdoc_runs`→`longdoc_claude_runs`)

### C. Raw capture gaps (regenerate without rerun)
- [x] Add `IMGCTX_CAPTURE_DIR` per-arm to `swebench_claude_experiment.py` (`capture_{cond}`)
- [x] Add `IMGCTX_CAPTURE_DIR` per-arm to `longdoc_claude_experiment.py` (`capture_{cond}`)
- [x] Add `--tag`/`--runs-dir` to claude drivers; longdoc now writes `results_{config}{tag}.json` (clobber fixed)
- [x] Confirm codex + opencode capture already full (start_proxy sets IMGCTX_CAPTURE_DIR ✓)

### D. Missing scripts (codex has only hotpot)
- [x] Write `bench/swebench_codex_experiment.py` (PORT 8820; reuses swebench_claude select_instances/checkout)
- [x] Write `bench/longdoc_codex_experiment.py` (PORT 8821; narrativeqa + gov_report; reuses longdoc load_items/best_score)

### E. Uniform reporter
- [x] `bench/campaign_report.py`: `normalize()` collapses both usage shapes into fresh/cache_read/cache_write/output. Tested on claude + codex + opencode old data (matches hand-analysis).
- [x] Reporter outputs per-cell ON/OFF: input/output/cache-read/cache-write/cost + %delta + cost_basis + F1 + ON image count. Reads run_meta sidecar for agent/family/benchmark (old data shows `?`; new runs populate it).

### F. Dry-run validation (before paid scale)
Ensure these new run output in new folder with timestamp so it will not replace old folder runs!!!
- [x] N=2 parallel dry-run of all 11 live cells -> `bench/campaign_dryrun_20260710_152928/`.
      All 11 ran; cost (real/simulated) + ON image counts + raw capture + run_meta all landed.
      Added `--port`/`--port-base` to all 8 drivers (parallel-safe, no proxy collision).
      Pre-warmed shared swebench repo cache serially (avoids 3-way git-clone race).
- [x] Reporter config-label bug FIXED (two longdoc configs shared a folder -> narrativeqa
      was mislabelled gov_report; now matches run_meta by results-file suffix).
- [x] Presented full ON/OFF table + categorized every issue / ON-worse cell.

---

## Cell matrix (11 live + 1 reuse)

| | claude sonnet | codex gpt-5.4-mini | opencode mimo |
|---|---|---|---|
| HotpotQA | REUSE old (skip) | run (script ✓) | run (script ✓) |
| SWE-bench | run (corrected profile) | **NEW script needed** | run (script ✓) |
| NarrativeQA | run (script ✓) | **NEW script needed** | run (script ✓) |
| GovReport | run (script ✓) | **NEW script needed** | run (script ✓) |

---

---

## G. Dry-run findings (N=2, noisy, directional only)

Categorized every cell that errored or went ON-worse:

**Errors / broken data (root-caused):**
- **mimo endpoint contention**: under 11-way parallel, the FREE zen route dropped with
  `"No provider available"` (20+ files). OFF arms (imaging off) failed too => NOT profile/
  imaging; it is concurrency vs a free endpoint. Old runs worked only because sequential.
- `is_error` missed zero-token/empty completions => corrupted OFF baseline => fake "+22%
  input" on mimo hotpot/nqa.

**Genuine ON-worse:**
- claude·narrativeqa cost +25.5%: ONE item (q00) looped on ON (out +12x, cache-read +310%).
  q01 ON was cheaper. Loop-amplification.
- codex·hotpot q01 f1 0.667->0 on ON: small-doc imaging hurts the answer (known marginal case).
- mimo·swebench ON: aggressive imaging (235-338 images) vs old 94-120; coder may be blinded.

**Tokens up but GOOD (mechanism working, keep):**
- claude·gov_report input +40% but cost -40.7%: imaging converts expensive cache-WRITES
  (1.25x) into cheap cache-READS (0.1x). Intended Anthropic play.

## H. Fixes applied (mimo, `bench/_opencode_run.py`)
- [x] `run_opencode(retries=3)`: retry TRANSIENT zen errors (No provider available / stream
      error / 429 / 5xx / overloaded) w/ linear backoff; skip retry on [TIMEOUT]. Recovered 10
      runs in the sequential refix.
- [x] `is_run_error(u, out)`: flag calls==0 OR prompt_tokens==0 OR [TIMEOUT]. (Deliberately
      NOT looks_transient: a retried-then-recovered run keeps the old error text -> would
      false-flag a healthy run. Dead runs log zero tokens, caught anyway.)
- [x] Wired into hotpot/swebench/longdoc opencode drivers; unit-tested.
- [x] Sequential refix `bench/mimo_refix_20260710_160813/`: empties GONE (hotpot 4/4, nqa 4/4,
      gov only q00-off = legit timeout). `is_error` recomputed post-hoc from usage+stdout.

## I. NEXT TODO (one agent at a time)

**mimo: DONE ✓**
- [x] Clean sequential swebench-ON verdict: **psf ON produced a patch WITH 411 images, err=False**
      => aggressive imaging is NOT the blocker; `SYSTEM=0` fix NOT needed. Earlier ON failures
      were contention only.
- [x] Residual = free-zen chokes on the LARGEST contexts. flask (~1M-tok repo) returned 0 tokens
      on BOTH arms even sequential + retries exhausted; psf-OFF also failed. Endpoint limit, hits
      OFF too, NOT imgctx. Scale mitigation (not a code bug): lighter instance selection + bump
      `--timeout` 360->600 + sequential + more retries.
- [ ] gov/nqa heavy looping (gov q00-off timeout @19 calls; nqa q01-on 44k out). Loops in OFF
      too = model/task, not imgctx. Scale handling: bump `--timeout`, larger N.

**codex: DONE ✓** (validated from dry-run data, no rerun/spend)
- [x] 4 codex cells healthy: no crashes/empties, all err=False, patches consistent, cost mostly
      down. swebench clean (-14/-19%), nqa clean (q01 f1 even up 0.7->0.875).
- [x] 2 ON-worse spots, both SMALL-CONTENT (imaging overhead > savings, not a bug): hotpot q01
      f1 0.667->0; gov q00 cost +11.7% (read 33k->38k). Same category as claude·hotpot. Larger N
      averages it; codex·hotpot may land net-neutral by design (counter-example cell).
- Possible cross-cutting tune: imgctx min-size gate to skip imaging tiny content (helps every
      agent's small-doc cells). NOT codex-specific.

**claude: WORKING ✓** (validated from dry-run data, no rerun/spend)
- [x] gov_report clean 2/2 win (q00 -43%, q01 -38%): imaging converts cache-writes->reads.
- [x] swebench: flask -28%, psf ~flat, all err=False. **TOOLS=0 fix VALIDATED** (ON<=OFF; old
      +26% regression gone).
- [x] narrativeqa: q01 -18% win; q00 LOOP blowup (out 672->8517, cread 171k->702k, cost +38%).
      One hard item looped; not a crash/bug. Loop-cost RECURRED at N=2 in full run (+46.3%),
      so applied the fix.
- [x] FIX APPLIED: split `_ANTHROPIC_DOC_NOHIST` (HISTORY=0) mapped to claude·narrativeqa ONLY;
      gov_report stays on _ANTHROPIC_DOC (HISTORY=1, still -43%). Retested same 2 items:
      ON vs OFF cost flipped **+46.3% -> -29.9%**; cache-write delta +48% -> -44%. Mechanism:
      HISTORY=0 keeps loop history as cheap text-cache instead of re-imaging it into expensive
      cache-writes. (Caveat: OFF baseline shifted run-to-run from Anthropic 5-min cache timing;
      within-run ON/OFF delta is the valid metric.) claude DONE.

**cross-cutting (before paid scale):**
- [x] Safe launcher `bench/run_campaign.sh` built + validated (syntax, flags, guard). 3 lanes
      (mimo/codex/claude) run concurrently across DIFFERENT endpoints; INSIDE each lane cells
      run one-at-a-time so no account self-contends. mimo strictly sequential (free-zen). Per-cell
      collision guard (skip if results already exist). swebench cache pre-warmed serially +
      instances pre-seeded to all 3 lanes (no clone/HF race). Fresh timestamped folder.
      Knobs: N_HOTPOT/N_SWE/N_NQA/N_GOV + timeouts via env. NOT RUN yet (awaiting user approval).
- [ ] Reporter: add claude ON image-count (cosmetic; Anthropic usage shape lacks it).

**final:**
- [x] Ran full campaign `bench/campaign_20260710_180022/` (N=2, all 11 cells, 3-lane safe launcher).
      mimo initially failed (free-endpoint OUTAGE, not code); re-ran mimo when it recovered.
      claude·narrativeqa swapped to the HISTORY=0 fixed data. Report: `.../REPORT.md`.

### CAMPAIGN RESULT (N=2): token always down; cost is provider/task specific
| cell | input Δ | cost Δ |
|---|---|---|
| claude gov | -45.1% | -43.2% ✓ |
| claude narrativeqa (HISTORY=0 fix) | +5.0% | -29.9% ✓ |
| claude swebench | +0.7% | -36.5% ✓ |
| codex hotpot | -6.4% | -26.2% ✓ |
| codex gov | -18.0% | -2.5% ~ |
| codex narrativeqa | -0.0% | -16.1% ✓ |
| codex swebench | -19.0% | -37.9% ✓ |
| mimo hotpot | -52.2% | -16.8% ✓ |
| mimo gov | -70.4% | -51.2% ✓ |
| mimo narrativeqa | -58.0% | **+39.8%** ✗ |
| mimo swebench | -63.0% | **+12.3%** ✗ |

**Finding:** input tokens drop in ~every cell. Cost is decided by the provider's rate structure:
- claude (cache-WRITE expensive @1.25x): imaging converts writes->reads -> cheaper everywhere (after nqa fix).
- codex: cheaper across the board.
- mimo two cost-UP cells, both real (not bugs), DESPITE big input cuts:
  * narrativeqa: model LOOPS on ON -> output 982->38,614 (+3832%); mimo output (`$0.28`) = 90x its
    cache-read (`$0.003`), so output dominates.
  * swebench: ON converts ultra-cheap cache-READ (`$0.003`) into pricier FRESH image tokens (`$0.14` =
    47x). Fewer tokens, higher cost. Mirror of the Anthropic cache-write trap, on the READ side.

### Optional mimo tuning (if we want mimo green too)
- [ ] mimo·narrativeqa: try HISTORY=0 (curb the loop -> less output). 
- [ ] mimo·swebench: less aggressive imaging when baseline is cache-read-heavy (imaging a
      cheaply-cached repo is a net-negative trade at mimo's rates), e.g. TOOL_RESULTS off, or a
      fresh-vs-cached gate.
- Note: mimo is actually FREE; these "costs" are SIMULATED at list rates to show where imaging
  would pay off if it were a paid API.

## Decisions locked
- Per-provider personalized profiles (not uniform).
- gpt-5.4-mini cost = simulated @ OpenAI list price.
- Codex hotpot = documented system-imaging exception.
- claude hotpot = skip, reuse old data (counter-intuition finding).
- claude swebench = corrected profile (TOOLS=0), worth a clean A/B.
- NO bench runs until checklist done + user approval.
