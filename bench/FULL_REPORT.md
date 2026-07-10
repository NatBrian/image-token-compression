# Full benchmark report — all runs

_Generated from 16 run folders; 52 (file × benchmark) runs. Every number regenerated from captured results — nothing rerun._

**Cost columns:** REAL = provider/endpoint-reported (verbatim); SIMULATED = tokens × per-model list rate (labelled per run). Both shown so the final report can pick either.

### Rate tables used for SIMULATED cost (USD / 1M tokens)

| model class | fresh | cache-write | cache-read | output | source |
|---|--:|--:|--:|--:|---|
| anthropic_sonnet | 3.0 | 3.75 | 0.3 | 15.0 | Anthropic claude-sonnet list |
| anthropic_haiku | 1.0 | 1.25 | 0.1 | 5.0 | Anthropic claude-haiku list |
| openai_gpt54mini | 0.75 | 0.0 | 0.075 | 4.5 | OpenAI gpt-5.4-mini list |
| openai_gpt4omini | 0.15 | 0.0 | 0.075 | 0.6 | OpenAI gpt-4o-mini list |
| mimo | 0.14 | 0.0 | 0.003 | 0.28 | Xiaomi MiMo-V2.5 first-party list |
| gemini_flash_lite | 0.1 | 0.0 | 0.025 | 0.4 | Gemini 3.1 flash-lite approx list |

## Summary — every run (delta = ON vs OFF)

ON-regions column is the imgctx config (which text regions were rendered to images) as **SYS·TOOLS·TOOL_RES·USER·HIST**, 1=imaged 0=kept-as-text. Every benchmark used a different config, so the deltas are only comparable within the same region string. `*` = reconstructed from the driver at the run's commit (older runs); unmarked = recorded in run_meta.

Avg img/call = ON-arm images per model call (claude from the events backfill; codex/mimo/gemini from results). `‡` = >1 run shared one per-arm proxy log (claude longdoc nqa+gov; hotpot base/sonnet/haiku), so that figure is folder-level, not per-run. `—` for claude = uncaptured.

| run | agent | model | bench | N | ON regions | avg img/call | input Δ | real cost Δ | sim cost Δ |
|---|---|---|---|--:|:--:|--:|--:|--:|--:|
| campaign_20260710_180022/claude_longdoc/_gov_report | claude | sonnet | gov_report | 2+2 | `0·0·1·1·1` | 3.0‡ | -45.1% | -43.2% | -41.3% |
| campaign_dryrun_20260710_152928/claude_longdoc/_gov_report | claude | sonnet | gov_report | 2+2 | `0·0·1·1·1` | 3.8‡ | +40.1% | -40.7% | -30.6% |
| longdoc_claude_runs/ | claude | claude-sonnet | gov_report | 4+4 | `0·0·1·1·1*` | 5.7‡ | -13.2% | -14.8% | -12.2% |
| longdoc_claude_runs/_gov_report | claude | claude-sonnet | gov_report | 4+4 | `0·0·1·1·1*` | 5.7‡ | -13.2% | -14.8% | -12.2% |
| longdoc_opencode_runs_gemini_31_flash_lite/_gov_report | opencode | gemini-3.1-flash-lite | gov_report | 3+3 | `0·0·1·1·1*` | — | — | — | — |
| campaign_20260710_180022/mimo_longdoc/_gov_report | mimo | opencode/mimo-v2.5-free | gov_report | 2+2 | `1·1·1·1·1` | 10.5 | -70.4% | — | -51.2% |
| campaign_dryrun_20260710_152928/mimo_longdoc/_gov_report | mimo | opencode/mimo-v2.5-free | gov_report | 2+2 | `1·1·1·1·1` | 9.1 | -83.2% | — | -89.3% |
| longdoc_opencode_runs/_gov_report | opencode | mimo-v2.5-free | gov_report | 4+4 | `0·0·1·1·1*` | 1.2 | -39.4% | — | -47.5% |
| mimo_refix_20260710_160813/mimo_longdoc/_gov_report | mimo | opencode/mimo-v2.5-free | gov_report | 2+2 | `1·1·1·1·1` | 10.1 | +20.0% | — | +35.8% |
| campaign_20260710_180022/codex_longdoc/_gov_report | codex | gpt-5.4-mini | gov_report | 2+2 | `1·1·1·1·1` | 1.0 | -18.0% | — | -2.5% |
| campaign_dryrun_20260710_152928/codex_longdoc/_gov_report | codex | gpt-5.4-mini | gov_report | 2+2 | `1·1·1·1·1` | 1.6 | -23.3% | — | -27.6% |
| longdoc_opencode_runs/_gov_report_gpt4omini | opencode | gpt-4o-mini | gov_report | 1+1 | `0·0·1·1·1*` | — | — | — | — |
| longdoc_opencode_runs_gpt_54_mini/_gov_report | opencode | gpt-5.4-mini | gov_report | 1+1 | `0·0·1·1·1*` | 0.0 | -44.0% | — | -9.5% |
| hotpot_claude_runs/ | claude | claude-sonnet | hotpot | 5+5 | `0·1·1·1·1*` | 13.1‡ | -35.1% | +44.0% | +31.6% |
| hotpot_claude_runs/_haiku | claude | claude-haiku | hotpot | 5+5 | `0·1·1·1·1*` | 13.1‡ | -29.4% | +124.8% | +124.8% |
| hotpot_claude_runs/_sonnet | claude | claude-sonnet | hotpot | 5+5 | `0·1·1·1·1*` | 13.1‡ | -35.1% | +8.0% | +8.0% |
| hotpot_claude_runs/_tools0 | claude | claude-sonnet | hotpot | 5+5 | `0·0·1·1·1*` | 0.1 | -0.2% | -25.4% | -21.6% |
| hotpot_verify_runs/claude_sonnet/ | claude | claude-sonnet | hotpot | 1+1 | `0·1·1·1·1*` | 13.0 | -34.8% | -32.7% | -32.0% |
| hotpot_opencode_runs_gemini_31_flash_lite_v2/ | opencode | gemini-3.1-flash-lite | hotpot | 3+3 | `0·1·1·1·1*` | 2.8 | -19.0% | — | -12.6% |
| campaign_20260710_180022/mimo_hotpot/ | mimo | opencode/mimo-v2.5-free | hotpot | 2+2 | `1·1·1·1·1` | 7.0 | -52.2% | — | -16.8% |
| campaign_dryrun_20260710_152928/mimo_hotpot/ | mimo | opencode/mimo-v2.5-free | hotpot | 2+2 | `1·1·1·1·1` | 7.8 | +22.1% | — | +5.1% |
| hotpot_runs/ | opencode | mimo-v2.5-free | hotpot | 10+10 | `1·1·1·1·1*` | 8.1 | -32.6% | — | -28.0% |
| hotpot_verify_runs/opencode_mimo/_mimo | opencode | mimo-v2.5-free | hotpot | 1+1 | `0·1·1·1·1*` | 3.3 | -12.0% | — | -8.0% |
| mimo_refix_20260710_160813/mimo_hotpot/ | mimo | opencode/mimo-v2.5-free | hotpot | 2+2 | `1·1·1·1·1` | 7.5 | -24.4% | — | +37.3% |
| campaign_20260710_180022/codex_hotpot/ | codex | gpt-5.4-mini | hotpot | 2+2 | `1·1·1·1·1` | 0.8 | -6.4% | — | -26.2% |
| campaign_dryrun_20260710_152928/codex_hotpot/ | codex | gpt-5.4-mini | hotpot | 2+2 | `1·1·1·1·1` | 1.5 | -35.1% | — | -13.9% |
| hotpot_opencode_runs/_gpt4omini | opencode | gpt-4o-mini | hotpot | 1+1 | `0·1·1·1·1*` | 5.1 | +3433.5% | — | +5776.5% |
| hotpot_verify_runs/codex/ | codex | gpt-5.4-mini | hotpot | 1+1 | `1·1·1·1·1*` | 0.9 | -35.2% | — | -42.2% |
| hotpot_verify_runs/opencode_oauth/_gpt54mini | opencode | gpt-5.4-mini | hotpot | 1+1 | `0·1·1·1·1*` | 2.7 | -5.6% | — | -5.7% |
| campaign_20260710_180022/claude_longdoc/_narrativeqa | claude | sonnet | narrativeqa | 2+2 | `0·0·1·1·0` | 3.0‡ | +5.0% | -29.9% | -23.4% |
| campaign_dryrun_20260710_152928/claude_longdoc/_narrativeqa | claude | sonnet | narrativeqa | 2+2 | `0·0·1·1·1` | 3.8‡ | +92.8% | +25.5% | +41.5% |
| claude_nqa_hist0_20260710_182803/_narrativeqa | claude | sonnet | narrativeqa | 2+2 | `0·0·1·1·0` | 4.8 | +5.0% | -29.9% | -23.4% |
| longdoc_claude_runs/_narrativeqa | claude | claude-sonnet | narrativeqa | 6+6 | `0·0·1·1·1*` | 5.7‡ | -15.7% | -28.7% | -24.9% |
| longdoc_opencode_runs_gemini_31_flash_lite/_narrativeqa | opencode | gemini-3.1-flash-lite | narrativeqa | 3+3 | `0·0·1·1·1*` | — | — | — | — |
| campaign_20260710_180022/mimo_longdoc/_narrativeqa | mimo | opencode/mimo-v2.5-free | narrativeqa | 2+2 | `1·1·1·1·1` | 8.9 | -58.0% | — | +39.8% |
| campaign_dryrun_20260710_152928/mimo_longdoc/_narrativeqa | mimo | opencode/mimo-v2.5-free | narrativeqa | 2+2 | `1·1·1·1·1` | 11.0 | +0.8% | — | -35.1% |
| longdoc_opencode_runs/_narrativeqa | opencode | mimo-v2.5-free | narrativeqa | 6+6 | `0·0·1·1·1*` | 4.0 | -27.1% | — | -51.2% |
| mimo_refix_20260710_160813/mimo_longdoc/_narrativeqa | mimo | opencode/mimo-v2.5-free | narrativeqa | 2+2 | `1·1·1·1·1` | 9.7 | -59.3% | — | +11.5% |
| campaign_20260710_180022/codex_longdoc/_narrativeqa | codex | gpt-5.4-mini | narrativeqa | 2+2 | `1·1·1·1·1` | 0.9 | -0.0% | — | -16.1% |
| campaign_dryrun_20260710_152928/codex_longdoc/_narrativeqa | codex | gpt-5.4-mini | narrativeqa | 2+2 | `1·1·1·1·1` | 1.8 | -36.0% | — | -13.8% |
| longdoc_opencode_runs/_narrativeqa_gpt4omini | opencode | gpt-4o-mini | narrativeqa | 1+1 | `0·0·1·1·1*` | — | — | — | — |
| longdoc_opencode_runs_gpt_54_mini/_narrativeqa | opencode | gpt-5.4-mini | narrativeqa | 1+1 | `0·0·1·1·1*` | 5.5 | +116.5% | — | +243.4% |
| campaign_20260710_180022/claude_swebench/ | claude | sonnet | swebench | 2+2 | `0·0·1·0·0` | 0.0 | +0.7% | -36.5% | -30.4% |
| campaign_dryrun_20260710_152928/claude_swebench/ | claude | sonnet | swebench | 2+2 | `0·0·1·0·0` | 0.0 | -27.5% | -15.3% | -17.3% |
| swebench_claude_runs/ | claude | claude-sonnet | swebench | 5+5 | `0·1·1·1·1*` | 13.5 | -24.7% | +26.5% | +13.8% |
| swebench_opencode_runs_gemini_31_flash_lite/ | opencode | gemini-3.1-flash-lite | swebench | 2+2 | `0·1·1·1·1*` | 10.1 | +90.5% | — | +83.1% |
| campaign_20260710_180022/mimo_swebench/ | mimo | opencode/mimo-v2.5-free | swebench | 2+2 | `1·1·1·1·1` | 14.5 | -63.0% | — | +12.3% |
| campaign_dryrun_20260710_152928/mimo_swebench/ | mimo | opencode/mimo-v2.5-free | swebench | 2+2 | `1·1·1·1·1` | 11.7 | -63.3% | — | -18.2% |
| mimo_refix_20260710_160813/mimo_swebench/ | mimo | opencode/mimo-v2.5-free | swebench | 2+2 | `1·1·1·1·1` | 9.3 | +59.0% | — | +339.9% |
| swebench_opencode_runs/ | opencode | mimo-v2.5-free | swebench | 5+5 | `0·1·1·1·1*` | 8.7 | -28.7% | — | +62.0% |
| campaign_20260710_180022/codex_swebench/ | codex | gpt-5.4-mini | swebench | 2+2 | `1·1·1·1·1` | 0.8 | -19.0% | — | -37.9% |
| campaign_dryrun_20260710_152928/codex_swebench/ | codex | gpt-5.4-mini | swebench | 2+2 | `1·1·1·1·1` | 1.6 | -29.8% | — | -15.8% |

## Detailed runs


# ▶ Benchmark: gov_report

### `campaign_20260710_180022/claude_longdoc/results_gov_report.json` — gov_report
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 1,141,314 | 626,593 | -45.1% |
| · fresh | 11,427 | 11,272 | -1.4% |
| · cache-read | 1,064,045 | 583,662 | -45.1% |
| · cache-write | 65,842 | 31,659 | -51.9% |
| output | 5,650 | 4,983 | -11.8% |
| avg calls/turns | 7.5 | 5.0 | -33.3% |
| ON images (sum) | — | 30 | ‡events-backfill, shared per-arm log across 2 runs (folder-level, not per-run) |
| ON avg img / call | — | 3.00 | over 10 imaging calls |
| **cost REAL** | `$0.8333` | `$0.4736` | -43.2% |
| **cost SIMULATED** | `$0.6852` | `$0.4024` | -41.3% |
| F1 (avg) | 0.121 | 0.101 | -16.5% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 49 | 50 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 5 | 5,636 | 300,018 | 23,780 | 1,945 | — | `$0.2788` | `$0.2253` | f1=0.09 |  |
| q00 | on | 5 | 5,636 | 290,261 | 14,597 | 3,074 | — | `$0.2377` | `$0.2048` | f1=0.10 |  |
| q01 | off | 10 | 5,791 | 764,027 | 42,062 | 3,705 | — | `$0.5545` | `$0.4599` | f1=0.15 |  |
| q01 | on | 5 | 5,636 | 293,401 | 17,062 | 1,909 | — | `$0.2359` | `$0.1975` | f1=0.10 |  |

</details>

### `campaign_dryrun_20260710_152928/claude_longdoc/results_gov_report.json` — gov_report
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 363,474 | 509,284 | +40.1% |
| · fresh | 11,262 | 11,268 | +0.1% |
| · cache-read | 234,813 | 454,881 | +93.7% |
| · cache-write | 117,399 | 43,135 | -63.3% |
| output | 3,117 | 5,236 | +68.0% |
| avg calls/turns | 2.5 | 4.0 | +60.0% |
| ON images (sum) | — | 84 | ‡events-backfill, shared per-arm log across 2 runs (folder-level, not per-run) |
| ON avg img / call | — | 3.82 | over 22 imaging calls |
| **cost REAL** | `$0.8554` | `$0.5076` | -40.7% |
| **cost SIMULATED** | `$0.5912` | `$0.4106` | -30.6% |
| F1 (avg) | 0.093 | 0.078 | -16.1% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 30 | 49 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 53,091 | 75,309 | 1,646 | — | `$0.5094` | `$0.3399` | f1=0.09 |  |
| q00 | on | 6 | 5,638 | 358,338 | 17,924 | 4,042 | — | `$0.2926` | `$0.2523` | f1=0.07 |  |
| q01 | off | 3 | 5,632 | 181,722 | 42,090 | 1,471 | — | `$0.3460` | `$0.2513` | f1=0.10 |  |
| q01 | on | 2 | 5,630 | 96,543 | 25,211 | 1,194 | — | `$0.2150` | `$0.1583` | f1=0.09 |  |

</details>

### `longdoc_claude_runs/results.json` — gov_report
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_claude_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 4 | 4 | +0.0% |
| errors | 0 | 0 | — |
| input total | 2,038,158 | 1,769,692 | -13.2% |
| · fresh | 22,850 | 22,703 | -0.6% |
| · cache-read | 1,893,249 | 1,657,109 | -12.5% |
| · cache-write | 122,059 | 89,880 | -26.4% |
| output | 8,748 | 11,607 | +32.7% |
| avg calls/turns | 7.0 | 6.8 | -3.6% |
| ON images (sum) | — | 155 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 5.74 | over 27 imaging calls |
| **cost REAL** | `$1.5001` | `$1.2786` | -14.8% |
| **cost SIMULATED** | `$1.2255` | `$1.0764` | -12.2% |
| F1 (avg) | 0.102 | 0.123 | +21.1% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 41 | 72 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 10 | 5,791 | 669,297 | 35,848 | 2,403 | — | `$0.4693` | `$0.3886` | f1=0.10 |  |
| q00 | on | 3 | 5,632 | 159,956 | 23,069 | 2,859 | — | `$0.2462` | `$0.1943` | f1=0.11 |  |
| q01 | off | 10 | 5,791 | 751,866 | 42,321 | 3,201 | — | `$0.5449` | `$0.4497` | f1=0.19 |  |
| q01 | on | 7 | 5,640 | 449,689 | 18,898 | 2,760 | — | `$0.3066` | `$0.2641` | f1=0.16 |  |
| q02 | off | 3 | 5,632 | 178,433 | 22,699 | 1,139 | — | `$0.2237` | `$0.1726` | f1=0.03 |  |
| q02 | on | 6 | 5,638 | 369,827 | 17,745 | 2,721 | — | `$0.2751` | `$0.2352` | f1=0.10 |  |
| q03 | off | 5 | 5,636 | 293,653 | 21,191 | 2,005 | — | `$0.2622` | `$0.2145` | f1=0.09 |  |
| q03 | on | 11 | 5,793 | 677,637 | 30,168 | 3,267 | — | `$0.4507` | `$0.3828` | f1=0.12 |  |

</details>

### `longdoc_claude_runs/results_gov_report.json` — gov_report
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_claude_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 4 | 4 | +0.0% |
| errors | 0 | 0 | — |
| input total | 2,038,158 | 1,769,692 | -13.2% |
| · fresh | 22,850 | 22,703 | -0.6% |
| · cache-read | 1,893,249 | 1,657,109 | -12.5% |
| · cache-write | 122,059 | 89,880 | -26.4% |
| output | 8,748 | 11,607 | +32.7% |
| avg calls/turns | 7.0 | 6.8 | -3.6% |
| ON images (sum) | — | 155 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 5.74 | over 27 imaging calls |
| **cost REAL** | `$1.5001` | `$1.2786` | -14.8% |
| **cost SIMULATED** | `$1.2255` | `$1.0764` | -12.2% |
| F1 (avg) | 0.102 | 0.123 | +21.1% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 41 | 72 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 10 | 5,791 | 669,297 | 35,848 | 2,403 | — | `$0.4693` | `$0.3886` | f1=0.10 |  |
| q00 | on | 3 | 5,632 | 159,956 | 23,069 | 2,859 | — | `$0.2462` | `$0.1943` | f1=0.11 |  |
| q01 | off | 10 | 5,791 | 751,866 | 42,321 | 3,201 | — | `$0.5449` | `$0.4497` | f1=0.19 |  |
| q01 | on | 7 | 5,640 | 449,689 | 18,898 | 2,760 | — | `$0.3066` | `$0.2641` | f1=0.16 |  |
| q02 | off | 3 | 5,632 | 178,433 | 22,699 | 1,139 | — | `$0.2237` | `$0.1726` | f1=0.03 |  |
| q02 | on | 6 | 5,638 | 369,827 | 17,745 | 2,721 | — | `$0.2751` | `$0.2352` | f1=0.10 |  |
| q03 | off | 5 | 5,636 | 293,653 | 21,191 | 2,005 | — | `$0.2622` | `$0.2145` | f1=0.09 |  |
| q03 | on | 11 | 5,793 | 677,637 | 30,168 | 3,267 | — | `$0.4507` | `$0.3828` | f1=0.12 |  |

</details>

### `longdoc_opencode_runs_gemini_31_flash_lite/results_gov_report.json` — gov_report
agent **opencode** · model **gemini-3.1-flash-lite** · family **google** · sim-rate _Gemini 3.1 flash-lite approx list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@094debc (junk: provider dropped mid-run)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 3 | 3 | +0.0% |
| errors | 3 | 3 | — |
| input total | 0 | 0 | — |
| · fresh | 0 | 0 | — |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 0 | 0 | — |
| avg calls/turns | 0.0 | 0.0 | — |
| ON images (sum) | — | 0 | results |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0000` | `$0.0000` | — |
| F1 (avg) | 0.000 | 0.000 | — |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 20 | 19 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q00 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q01 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q01 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q02 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q02 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |

</details>

### `campaign_20260710_180022/mimo_longdoc/results_gov_report.json` — gov_report
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 1,780,375 | 527,462 | -70.4% |
| · fresh | 143,895 | 72,230 | -49.8% |
| · cache-read | 1,636,480 | 455,232 | -72.2% |
| · cache-write | 0 | 0 | — |
| output | 17,542 | 11,188 | -36.2% |
| avg calls/turns | 33.5 | 19.0 | -43.3% |
| ON images (sum) | — | 399 | results |
| ON avg img / call | — | 10.50 | over 38 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0300` | `$0.0146` | -51.2% |
| F1 (avg) | 0.136 | 0.135 | -0.7% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 159 | 281 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 37 | 65,299 | 899,456 | 0 | 8,112 | 0 | — | `$0.0141` | f1=0.14 |  |
| q00 | on | 23 | 49,083 | 272,960 | 0 | 5,627 | 253 | — | `$0.0093` | f1=0.13 |  |
| q01 | off | 30 | 78,596 | 737,024 | 0 | 9,430 | 0 | — | `$0.0159` | f1=0.13 |  |
| q01 | on | 15 | 23,147 | 182,272 | 0 | 5,561 | 146 | — | `$0.0053` | f1=0.14 |  |

</details>

### `campaign_dryrun_20260710_152928/mimo_longdoc/results_gov_report.json` — gov_report
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 445,567 | 74,818 | -83.2% |
| · fresh | 83,711 | 6,978 | -91.7% |
| · cache-read | 361,856 | 67,840 | -81.3% |
| · cache-write | 0 | 0 | — |
| output | 1,728 | 842 | -51.3% |
| avg calls/turns | 11.0 | 7.0 | -36.4% |
| ON images (sum) | — | 128 | results |
| ON avg img / call | — | 9.14 | over 14 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0133` | `$0.0014` | -89.3% |
| F1 (avg) | 0.128 | 0.049 | -61.7% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 47 | 80 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 13 | 44,085 | 219,200 | 0 | 1,133 | 0 | — | `$0.0071` | f1=0.12 |  |
| q00 | on | 2 | 0 | 0 | 0 | 0 | 11 | — | `$0.0000` | f1=0.00 |  |
| q01 | off | 9 | 39,626 | 142,656 | 0 | 595 | 0 | — | `$0.0061` | f1=0.14 |  |
| q01 | on | 12 | 6,978 | 67,840 | 0 | 842 | 117 | — | `$0.0014` | f1=0.10 |  |

</details>

### `longdoc_opencode_runs/results_gov_report.json` — gov_report
agent **opencode** · model **mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@2327fd7_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 4 | 4 | +0.0% |
| errors | 0 | 0 | — |
| input total | 763,068 | 462,073 | -39.4% |
| · fresh | 81,788 | 31,161 | -61.9% |
| · cache-read | 681,280 | 430,912 | -36.7% |
| · cache-write | 0 | 0 | — |
| output | 10,287 | 10,520 | +2.3% |
| avg calls/turns | 7.8 | 5.8 | -25.8% |
| ON images (sum) | — | 27 | results |
| ON avg img / call | — | 1.17 | over 23 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0164` | `$0.0086` | -47.5% |
| F1 (avg) | 0.130 | 0.125 | -4.0% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 31 | 40 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 11 | 14,757 | 265,088 | 0 | 3,573 | 0 | — | `$0.0039` | f1=0.16 |  |
| q00 | on | 5 | 7,542 | 89,408 | 0 | 2,489 | 6 | — | `$0.0020` | f1=0.14 |  |
| q01 | off | 5 | 13,405 | 88,896 | 0 | 544 | 0 | — | `$0.0023` | f1=0.14 |  |
| q01 | on | 6 | 8,237 | 112,960 | 0 | 2,290 | 6 | — | `$0.0021` | f1=0.14 |  |
| q02 | off | 9 | 41,451 | 213,888 | 0 | 3,508 | 0 | — | `$0.0074` | f1=0.09 |  |
| q02 | on | 7 | 8,392 | 139,200 | 0 | 2,902 | 10 | — | `$0.0024` | f1=0.16 |  |
| q03 | off | 6 | 12,175 | 113,408 | 0 | 2,662 | 0 | — | `$0.0028` | f1=0.13 |  |
| q03 | on | 5 | 6,990 | 89,344 | 0 | 2,839 | 5 | — | `$0.0020` | f1=0.07 |  |

</details>

### `mimo_refix_20260710_160813/mimo_longdoc/results_gov_report.json` — gov_report
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 1 | 0 | — |
| input total | 383,571 | 460,455 | +20.0% |
| · fresh | 36,563 | 43,111 | +17.9% |
| · cache-read | 347,008 | 417,344 | +20.3% |
| · cache-write | 0 | 0 | — |
| output | 9,784 | 17,123 | +75.0% |
| avg calls/turns | 22.5 | 29.0 | +28.9% |
| ON images (sum) | — | 586 | results |
| ON avg img / call | — | 10.10 | over 58 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0089` | `$0.0121` | +35.8% |
| F1 (avg) | 0.049 | 0.100 | +105.2% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 250 | 383 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 19 | 11,871 | 92,288 | 0 | 2,334 | 0 | — | `$0.0026` | f1=0.00 | Y |
| q00 | on | 32 | 21,076 | 235,840 | 0 | 9,166 | 326 | — | `$0.0062` | f1=0.10 |  |
| q01 | off | 26 | 24,692 | 254,720 | 0 | 7,450 | 0 | — | `$0.0063` | f1=0.10 |  |
| q01 | on | 26 | 22,035 | 181,504 | 0 | 7,957 | 260 | — | `$0.0059` | f1=0.10 |  |

</details>

### `campaign_20260710_180022/codex_longdoc/results_gov_report.json` — gov_report
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 165,623 | 135,792 | -18.0% |
| · fresh | 16,375 | 26,992 | +64.8% |
| · cache-read | 149,248 | 108,800 | -27.1% |
| · cache-write | 0 | 0 | — |
| output | 3,776 | 2,454 | -35.0% |
| avg calls/turns | 16.0 | 16.0 | +0.0% |
| ON images (sum) | — | 32 | results |
| ON avg img / call | — | 1.00 | over 32 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0405` | `$0.0394` | -2.5% |
| F1 (avg) | 0.015 | 0.011 | -25.8% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 46 | 45 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 18 | 6,223 | 81,408 | 0 | 1,947 | 0 | — | `$0.0195` | f1=0.02 |  |
| q00 | on | 18 | 18,718 | 61,440 | 0 | 1,424 | 20 | — | `$0.0251` | f1=0.01 |  |
| q01 | off | 14 | 10,152 | 67,840 | 0 | 1,829 | 0 | — | `$0.0209` | f1=0.01 |  |
| q01 | on | 14 | 8,274 | 47,360 | 0 | 1,030 | 12 | — | `$0.0144` | f1=0.01 |  |

</details>

### `campaign_dryrun_20260710_152928/codex_longdoc/results_gov_report.json` — gov_report
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 92,454 | 70,928 | -23.3% |
| · fresh | 15,270 | 11,024 | -27.8% |
| · cache-read | 77,184 | 59,904 | -22.4% |
| · cache-write | 0 | 0 | — |
| output | 2,773 | 1,949 | -29.7% |
| avg calls/turns | 5.5 | 5.0 | -9.1% |
| ON images (sum) | — | 16 | results |
| ON avg img / call | — | 1.60 | over 10 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0297` | `$0.0215` | -27.6% |
| F1 (avg) | 0.009 | 0.015 | +63.2% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 35 | 38 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 5 | 6,160 | 33,280 | 0 | 1,117 | 0 | — | `$0.0121` | f1=0.01 |  |
| q00 | on | 6 | 7,388 | 38,272 | 0 | 1,144 | 10 | — | `$0.0136` | f1=0.02 |  |
| q01 | off | 6 | 9,110 | 43,904 | 0 | 1,656 | 0 | — | `$0.0176` | f1=0.01 |  |
| q01 | on | 4 | 3,636 | 21,632 | 0 | 805 | 6 | — | `$0.0080` | f1=0.01 |  |

</details>

### `longdoc_opencode_runs/results_gov_report_gpt4omini.json` — gov_report
agent **opencode** · model **gpt-4o-mini** · family **openai** · sim-rate _OpenAI gpt-4o-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@2327fd7_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 1 | 1 | — |
| input total | 0 | 0 | — |
| · fresh | 0 | 0 | — |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 0 | 0 | — |
| avg calls/turns | 0.0 | 0.0 | — |
| ON images (sum) | — | 0 | results |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0000` | `$0.0000` | — |
| F1 (avg) | 0.004 | 0.004 | +0.0% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 13 | 13 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q00 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |

</details>

### `longdoc_opencode_runs_gpt_54_mini/results_gov_report.json` — gov_report
agent **opencode** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@162ccbe_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 65,112 | 36,435 | -44.0% |
| · fresh | 12,888 | 19,027 | +47.6% |
| · cache-read | 52,224 | 17,408 | -66.7% |
| · cache-write | 0 | 0 | — |
| output | 1,152 | 313 | -72.8% |
| avg calls/turns | 4.0 | 3.0 | -25.0% |
| ON images (sum) | — | 0 | results |
| ON avg img / call | — | 0.00 | over 3 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0188` | `$0.0170` | -9.5% |
| F1 (avg) | 0.105 | 0.071 | -32.4% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 84 | 16 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 4 | 12,888 | 52,224 | 0 | 1,152 | 0 | — | `$0.0188` | f1=0.10 |  |
| q00 | on | 3 | 19,027 | 17,408 | 0 | 313 | 0 | — | `$0.0170` | f1=0.07 |  |

</details>


# ▶ Benchmark: hotpot

### `hotpot_claude_runs/results.json` — hotpot
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_claude_experiment.py@2eb3f56_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 0 | — |
| input total | 592,748 | 384,822 | -35.1% |
| · fresh | 28,150 | 28,150 | +0.0% |
| · cache-read | 478,520 | 201,585 | -57.9% |
| · cache-write | 86,078 | 155,087 | +80.2% |
| output | 703 | 807 | +14.8% |
| avg calls/turns | 2.0 | 2.0 | +0.0% |
| ON images (sum) | — | 131 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 13.10 | over 10 imaging calls |
| **cost REAL** | `$0.7550` | `$1.0876` | +44.0% |
| **cost SIMULATED** | `$0.5613` | `$0.7386` | +31.6% |
| F1 (avg) | 0.848 | 0.684 | -19.3% |
| contains (avg) | 0.800 | 0.800 | — |
| avg duration s | 9 | 26 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 95,696 | 17,128 | 123 | — | `$0.1502` | `$0.1117` | f1=1.00 |  |
| q00 | on | 2 | 5,630 | 40,309 | 31,220 | 122 | — | `$0.2181` | `$0.1479` | f1=1.00 |  |
| q01 | off | 2 | 5,630 | 95,705 | 17,106 | 176 | — | `$0.1509` | `$0.1124` | f1=0.67 |  |
| q01 | on | 2 | 5,630 | 40,318 | 31,222 | 173 | — | `$0.2189` | `$0.1487` | f1=0.67 |  |
| q02 | off | 2 | 5,630 | 95,714 | 17,632 | 130 | — | `$0.1533` | `$0.1137` | f1=1.00 |  |
| q02 | on | 2 | 5,630 | 40,327 | 30,224 | 196 | — | `$0.2133` | `$0.1453` | f1=1.00 |  |
| q03 | off | 2 | 5,630 | 95,705 | 16,905 | 155 | — | `$0.1494` | `$0.1113` | f1=1.00 |  |
| q03 | on | 2 | 5,630 | 40,318 | 31,019 | 169 | — | `$0.2176` | `$0.1478` | f1=0.18 |  |
| q04 | off | 2 | 5,630 | 95,700 | 17,307 | 119 | — | `$0.1512` | `$0.1123` | f1=0.57 |  |
| q04 | on | 2 | 5,630 | 40,313 | 31,402 | 147 | — | `$0.2196` | `$0.1489` | f1=0.57 |  |

</details>

### `hotpot_claude_runs/results_haiku.json` — hotpot
agent **claude** · model **claude-haiku** · family **anthropic** · sim-rate _Anthropic claude-haiku list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_claude_experiment.py@2eb3f56_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 0 | — |
| input total | 448,040 | 316,220 | -29.4% |
| · fresh | 90 | 90 | +0.0% |
| · cache-read | 382,896 | 93,965 | -75.5% |
| · cache-write | 65,054 | 222,165 | +241.5% |
| output | 3,044 | 3,208 | +5.4% |
| avg calls/turns | 2.0 | 2.0 | +0.0% |
| ON images (sum) | — | 131 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 13.10 | over 10 imaging calls |
| **cost REAL** | `$0.1349` | `$0.3032` | +124.8% |
| **cost SIMULATED** | `$0.1349` | `$0.3032` | +124.8% |
| F1 (avg) | 0.848 | 0.860 | +1.5% |
| contains (avg) | 0.800 | 1.000 | — |
| avg duration s | 13 | 32 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 18 | 76,572 | 12,876 | 322 | — | `$0.0254` | `$0.0254` | f1=1.00 |  |
| q00 | on | 2 | 18 | 18,793 | 44,493 | 331 | — | `$0.0592` | `$0.0592` | f1=1.00 |  |
| q01 | off | 2 | 18 | 76,581 | 13,058 | 849 | — | `$0.0282` | `$0.0282` | f1=0.67 |  |
| q01 | on | 2 | 18 | 18,793 | 44,599 | 688 | — | `$0.0611` | `$0.0611` | f1=0.30 |  |
| q02 | off | 2 | 18 | 76,588 | 13,278 | 561 | — | `$0.0271` | `$0.0271` | f1=1.00 |  |
| q02 | on | 2 | 18 | 18,793 | 44,108 | 1,096 | — | `$0.0625` | `$0.0625` | f1=1.00 |  |
| q03 | off | 2 | 18 | 76,578 | 12,742 | 493 | — | `$0.0261` | `$0.0261` | f1=1.00 |  |
| q03 | on | 2 | 18 | 18,793 | 44,356 | 449 | — | `$0.0596` | `$0.0596` | f1=1.00 |  |
| q04 | off | 2 | 18 | 76,577 | 13,100 | 819 | — | `$0.0281` | `$0.0281` | f1=0.57 |  |
| q04 | on | 2 | 18 | 18,793 | 44,609 | 644 | — | `$0.0609` | `$0.0609` | f1=1.00 |  |

</details>

### `hotpot_claude_runs/results_sonnet.json` — hotpot
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_claude_experiment.py@2eb3f56_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 0 | — |
| input total | 592,554 | 384,529 | -35.1% |
| · fresh | 28,150 | 28,150 | +0.0% |
| · cache-read | 435,312 | 193,117 | -55.6% |
| · cache-write | 129,092 | 163,262 | +26.5% |
| output | 671 | 737 | +9.8% |
| avg calls/turns | 2.0 | 2.0 | +0.0% |
| ON images (sum) | — | 131 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 13.10 | over 10 imaging calls |
| **cost REAL** | `$0.2364` | `$0.2552` | +8.0% |
| **cost SIMULATED** | `$0.7092` | `$0.7657` | +8.0% |
| F1 (avg) | 0.848 | 0.848 | +0.0% |
| contains (avg) | 0.800 | 0.800 | — |
| avg duration s | 9 | 30 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 52,560 | 60,227 | 122 | — | `$0.0868` | `$0.2603` | f1=1.00 |  |
| q00 | on | 2 | 5,630 | 31,913 | 39,584 | 126 | — | `$0.0589` | `$0.1768` | f1=1.00 |  |
| q01 | off | 2 | 5,630 | 95,687 | 17,098 | 171 | — | `$0.0374` | `$0.1123` | f1=0.67 |  |
| q01 | on | 2 | 5,630 | 40,300 | 31,179 | 124 | — | `$0.0493` | `$0.1478` | f1=0.67 |  |
| q02 | off | 2 | 5,630 | 95,696 | 17,590 | 106 | — | `$0.0377` | `$0.1132` | f1=1.00 |  |
| q02 | on | 2 | 5,630 | 40,309 | 30,207 | 182 | — | `$0.0483` | `$0.1450` | f1=1.00 |  |
| q03 | off | 2 | 5,630 | 95,687 | 16,889 | 154 | — | `$0.0371` | `$0.1112` | f1=1.00 |  |
| q03 | on | 2 | 5,630 | 40,300 | 30,979 | 154 | — | `$0.0492` | `$0.1475` | f1=1.00 |  |
| q04 | off | 2 | 5,630 | 95,682 | 17,288 | 118 | — | `$0.0374` | `$0.1122` | f1=0.57 |  |
| q04 | on | 2 | 5,630 | 40,295 | 31,313 | 151 | — | `$0.0496` | `$0.1487` | f1=0.57 |  |

</details>

### `hotpot_claude_runs/results_tools0.json` — hotpot
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_claude_experiment.py --tools0 @92ab124_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 0 | — |
| input total | 591,677 | 590,283 | -0.2% |
| · fresh | 28,150 | 28,150 | +0.0% |
| · cache-read | 434,855 | 477,985 | +9.9% |
| · cache-write | 128,672 | 84,148 | -34.6% |
| output | 771 | 815 | +5.7% |
| avg calls/turns | 2.0 | 2.0 | +0.0% |
| ON images (sum) | — | 1 | events-backfill |
| ON avg img / call | — | 0.10 | over 10 imaging calls |
| **cost REAL** | `$0.9985` | `$0.7450` | -25.4% |
| **cost SIMULATED** | `$0.7090` | `$0.5556` | -21.6% |
| F1 (avg) | 0.848 | 0.848 | +0.0% |
| contains (avg) | 0.800 | 0.800 | — |
| avg duration s | 11 | 11 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 52,459 | 60,136 | 132 | — | `$0.3954` | `$0.2601` | f1=1.00 |  |
| q00 | on | 2 | 5,630 | 95,589 | 17,042 | 143 | — | `$0.1500` | `$0.1116` | f1=1.00 |  |
| q01 | off | 2 | 5,630 | 95,598 | 17,004 | 183 | — | `$0.1503` | `$0.1121` | f1=0.67 |  |
| q01 | on | 2 | 5,630 | 95,598 | 17,059 | 186 | — | `$0.1507` | `$0.1123` | f1=0.67 |  |
| q02 | off | 2 | 5,630 | 95,607 | 17,522 | 127 | — | `$0.1526` | `$0.1132` | f1=1.00 |  |
| q02 | on | 2 | 5,630 | 95,607 | 16,035 | 202 | — | `$0.1448` | `$0.1087` | f1=1.00 |  |
| q03 | off | 2 | 5,630 | 95,598 | 16,801 | 162 | — | `$0.1488` | `$0.1110` | f1=1.00 |  |
| q03 | on | 2 | 5,630 | 95,598 | 16,804 | 157 | — | `$0.1487` | `$0.1109` | f1=1.00 |  |
| q04 | off | 2 | 5,630 | 95,593 | 17,209 | 167 | — | `$0.1513` | `$0.1126` | f1=0.57 |  |
| q04 | on | 2 | 5,630 | 95,593 | 17,208 | 127 | — | `$0.1507` | `$0.1120` | f1=0.57 |  |

</details>

### `hotpot_verify_runs/claude_sonnet/results.json` — hotpot
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_claude_experiment.py@cb64fc3_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 119,504 | 77,954 | -34.8% |
| · fresh | 5,630 | 5,630 | +0.0% |
| · cache-read | 53,101 | 32,326 | -39.1% |
| · cache-write | 60,773 | 39,998 | -34.2% |
| output | 127 | 137 | +7.9% |
| avg calls/turns | 2.0 | 2.0 | +0.0% |
| ON images (sum) | — | 26 | events-backfill |
| ON avg img / call | — | 13.00 | over 2 imaging calls |
| **cost REAL** | `$0.3994` | `$0.2686` | -32.7% |
| **cost SIMULATED** | `$0.2626` | `$0.1786` | -32.0% |
| F1 (avg) | 1.000 | 1.000 | +0.0% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 8 | 25 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 53,101 | 60,773 | 127 | — | `$0.3994` | `$0.2626` | f1=1.00 |  |
| q00 | on | 2 | 5,630 | 32,326 | 39,998 | 137 | — | `$0.2686` | `$0.1786` | f1=1.00 |  |

</details>

### `hotpot_opencode_runs_gemini_31_flash_lite_v2/results.json` — hotpot
agent **opencode** · model **gemini-3.1-flash-lite** · family **google** · sim-rate _Gemini 3.1 flash-lite approx list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_opencode_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 3 | 3 | +0.0% |
| errors | 0 | 0 | — |
| input total | 162,261 | 131,392 | -19.0% |
| · fresh | 146,002 | 131,392 | -10.0% |
| · cache-read | 16,259 | 0 | -100.0% |
| · cache-write | 0 | 0 | — |
| output | 328 | 213 | -35.1% |
| avg calls/turns | 3.3 | 3.0 | -10.0% |
| ON images (sum) | — | 25 | results |
| ON avg img / call | — | 2.78 | over 9 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0151` | `$0.0132` | -12.6% |
| F1 (avg) | 0.767 | 0.667 | -13.0% |
| contains (avg) | 1.000 | 0.667 | — |
| avg duration s | 12 | 32 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 45,605 | 0 | 0 | 110 | 0 | — | `$0.0046` | f1=1.00 |  |
| q00 | on | 3 | 43,754 | 0 | 0 | 72 | 8 | — | `$0.0044` | f1=1.00 |  |
| q01 | off | 4 | 54,423 | 16,259 | 0 | 145 | 0 | — | `$0.0059` | f1=0.30 |  |
| q01 | on | 3 | 43,924 | 0 | 0 | 69 | 8 | — | `$0.0044` | f1=0.00 |  |
| q02 | off | 3 | 45,974 | 0 | 0 | 73 | 0 | — | `$0.0046` | f1=1.00 |  |
| q02 | on | 3 | 43,714 | 0 | 0 | 72 | 9 | — | `$0.0044` | f1=1.00 |  |

</details>

### `campaign_20260710_180022/mimo_hotpot/results.json` — hotpot
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 120,678 | 57,657 | -52.2% |
| · fresh | 10,022 | 6,457 | -35.6% |
| · cache-read | 110,656 | 51,200 | -53.7% |
| · cache-write | 0 | 0 | — |
| output | 1,160 | 2,342 | +101.9% |
| avg calls/turns | 3.5 | 3.0 | -14.3% |
| ON images (sum) | — | 42 | results |
| ON avg img / call | — | 7.00 | over 6 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0021` | `$0.0017` | -16.8% |
| F1 (avg) | 0.834 | 0.650 | -22.0% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 18 | 33 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 3,757 | 43,136 | 0 | 130 | 0 | — | `$0.0007` | f1=1.00 |  |
| q00 | on | 3 | 3,176 | 25,600 | 0 | 921 | 21 | — | `$0.0008` | f1=1.00 |  |
| q01 | off | 4 | 6,265 | 67,520 | 0 | 1,030 | 0 | — | `$0.0014` | f1=0.67 |  |
| q01 | on | 3 | 3,281 | 25,600 | 0 | 1,421 | 21 | — | `$0.0009` | f1=0.30 |  |

</details>

### `campaign_dryrun_20260710_152928/mimo_hotpot/results.json` — hotpot
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 46,905 | 57,268 | +22.1% |
| · fresh | 22,393 | 18,356 | -18.0% |
| · cache-read | 24,512 | 38,912 | +58.7% |
| · cache-write | 0 | 0 | — |
| output | 111 | 2,571 | +2216.2% |
| avg calls/turns | 3.5 | 4.0 | +14.3% |
| ON images (sum) | — | 62 | results |
| ON avg img / call | — | 7.75 | over 8 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0032` | `$0.0034` | +5.1% |
| F1 (avg) | 0.500 | 0.666 | +33.3% |
| contains (avg) | 0.500 | 1.000 | — |
| avg duration s | 12 | 43 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 5 | 22,393 | 24,512 | 0 | 111 | 0 | — | `$0.0032` | f1=1.00 |  |
| q00 | on | 3 | 15,021 | 13,312 | 0 | 499 | 21 | — | `$0.0023` | f1=1.00 |  |
| q01 | off | 2 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 |  |
| q01 | on | 5 | 3,335 | 25,600 | 0 | 2,072 | 41 | — | `$0.0011` | f1=0.33 |  |

</details>

### `hotpot_runs/results.json` — hotpot
agent **opencode** · model **mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (RECON): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_experiment.py@c1aa5e2 (defaults: all on)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 10 | 10 | +0.0% |
| errors | 0 | 0 | — |
| input total | 465,300 | 313,441 | -32.6% |
| · fresh | 465,300 | 313,441 | -32.6% |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 1,575 | 12,029 | +663.7% |
| avg calls/turns | 3.0 | 3.2 | +6.7% |
| ON images (sum) | — | 259 | results |
| ON avg img / call | — | 8.09 | over 32 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0656` | `$0.0472` | -28.0% |
| F1 (avg) | 0.757 | 0.879 | +16.1% |
| contains (avg) | 0.700 | 0.800 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 46,283 | 0 | 0 | 120 | 0 | — | `$0.0065` | f1=1.00 |  |
| q01 | off | 3 | 46,435 | 0 | 0 | 307 | 0 | — | `$0.0066` | f1=0.00 |  |
| q02 | off | 3 | 46,666 | 0 | 0 | 181 | 0 | — | `$0.0066` | f1=1.00 |  |
| q03 | off | 3 | 46,119 | 0 | 0 | 130 | 0 | — | `$0.0065` | f1=1.00 |  |
| q04 | off | 3 | 46,462 | 0 | 0 | 133 | 0 | — | `$0.0065` | f1=0.57 |  |
| q05 | off | 3 | 46,508 | 0 | 0 | 136 | 0 | — | `$0.0065` | f1=1.00 |  |
| q06 | off | 3 | 46,993 | 0 | 0 | 213 | 0 | — | `$0.0066` | f1=1.00 |  |
| q07 | off | 3 | 46,963 | 0 | 0 | 133 | 0 | — | `$0.0066` | f1=0.00 |  |
| q08 | off | 3 | 46,424 | 0 | 0 | 140 | 0 | — | `$0.0065` | f1=1.00 |  |
| q09 | off | 3 | 46,447 | 0 | 0 | 82 | 0 | — | `$0.0065` | f1=1.00 |  |
| q00 | on | 3 | 28,552 | 0 | 0 | 957 | 23 | — | `$0.0043` | f1=1.00 |  |
| q01 | on | 3 | 28,828 | 0 | 0 | 1,458 | 23 | — | `$0.0044` | f1=0.38 |  |
| q02 | on | 3 | 28,105 | 0 | 0 | 1,335 | 24 | — | `$0.0043` | f1=1.00 |  |
| q03 | on | 3 | 28,376 | 0 | 0 | 618 | 23 | — | `$0.0041` | f1=1.00 |  |
| q04 | on | 3 | 28,002 | 0 | 0 | 1,332 | 24 | — | `$0.0043` | f1=0.75 |  |
| q05 | on | 3 | 28,765 | 0 | 0 | 1,306 | 23 | — | `$0.0044` | f1=1.00 |  |
| q06 | on | 5 | 57,943 | 0 | 0 | 1,557 | 48 | — | `$0.0085` | f1=1.00 |  |
| q07 | on | 3 | 28,183 | 0 | 0 | 1,068 | 24 | — | `$0.0042` | f1=0.67 |  |
| q08 | on | 3 | 28,638 | 0 | 0 | 630 | 23 | — | `$0.0042` | f1=1.00 |  |
| q09 | on | 3 | 28,049 | 0 | 0 | 1,768 | 24 | — | `$0.0044` | f1=1.00 |  |

</details>

### `hotpot_verify_runs/opencode_mimo/results_mimo.json` — hotpot
agent **opencode** · model **mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_opencode_experiment.py@cb64fc3_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 46,879 | 41,231 | -12.0% |
| · fresh | 23,199 | 21,391 | -7.8% |
| · cache-read | 23,680 | 19,840 | -16.2% |
| · cache-write | 0 | 0 | — |
| output | 160 | 145 | -9.4% |
| avg calls/turns | 3.0 | 3.0 | +0.0% |
| ON images (sum) | — | 10 | results |
| ON avg img / call | — | 3.33 | over 3 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0034` | `$0.0031` | -8.0% |
| F1 (avg) | 1.000 | 1.000 | +0.0% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 11 | 18 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 23,199 | 23,680 | 0 | 160 | 0 | — | `$0.0034` | f1=1.00 |  |
| q00 | on | 3 | 21,391 | 19,840 | 0 | 145 | 10 | — | `$0.0031` | f1=1.00 |  |

</details>

### `mimo_refix_20260710_160813/mimo_hotpot/results.json` — hotpot
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 188,432 | 142,440 | -24.4% |
| · fresh | 10,640 | 11,368 | +6.8% |
| · cache-read | 177,792 | 131,072 | -26.3% |
| · cache-write | 0 | 0 | — |
| output | 2,255 | 5,930 | +163.0% |
| avg calls/turns | 8.5 | 12.5 | +47.1% |
| ON images (sum) | — | 187 | results |
| ON avg img / call | — | 7.48 | over 25 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0027` | `$0.0036` | +37.3% |
| F1 (avg) | 0.666 | 0.650 | -2.5% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 38 | 125 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 14 | 6,784 | 134,592 | 0 | 1,907 | 0 | — | `$0.0019` | f1=1.00 |  |
| q00 | on | 18 | 8,106 | 105,472 | 0 | 4,987 | 144 | — | `$0.0028` | f1=1.00 |  |
| q01 | off | 3 | 3,856 | 43,200 | 0 | 348 | 0 | — | `$0.0008` | f1=0.33 |  |
| q01 | on | 7 | 3,262 | 25,600 | 0 | 943 | 43 | — | `$0.0008` | f1=0.30 |  |

</details>

### `campaign_20260710_180022/codex_hotpot/results.json` — hotpot
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 72,049 | 67,442 | -6.4% |
| · fresh | 16,113 | 11,122 | -31.0% |
| · cache-read | 55,936 | 56,320 | +0.7% |
| · cache-write | 0 | 0 | — |
| output | 1,754 | 1,171 | -33.2% |
| avg calls/turns | 9.0 | 10.0 | +11.1% |
| ON images (sum) | — | 16 | results |
| ON avg img / call | — | 0.80 | over 20 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0242` | `$0.0178` | -26.2% |
| F1 (avg) | 0.834 | 0.500 | -40.0% |
| contains (avg) | 1.000 | 0.500 | — |
| avg duration s | 26 | 30 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 10 | 5,884 | 32,768 | 0 | 679 | 0 | — | `$0.0099` | f1=1.00 |  |
| q00 | on | 8 | 4,896 | 20,096 | 0 | 520 | 6 | — | `$0.0075` | f1=1.00 |  |
| q01 | off | 8 | 10,229 | 23,168 | 0 | 1,075 | 0 | — | `$0.0142` | f1=0.67 |  |
| q01 | on | 12 | 6,226 | 36,224 | 0 | 651 | 10 | — | `$0.0103` | f1=0.00 |  |

</details>

### `campaign_dryrun_20260710_152928/codex_hotpot/results.json` — hotpot
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 77,363 | 50,209 | -35.1% |
| · fresh | 12,339 | 13,089 | +6.1% |
| · cache-read | 65,024 | 37,120 | -42.9% |
| · cache-write | 0 | 0 | — |
| output | 1,391 | 1,100 | -20.9% |
| avg calls/turns | 5.0 | 4.0 | -20.0% |
| ON images (sum) | — | 12 | results |
| ON avg img / call | — | 1.50 | over 8 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0204` | `$0.0176` | -13.9% |
| F1 (avg) | 0.834 | 0.500 | -40.0% |
| contains (avg) | 1.000 | 0.500 | — |
| avg duration s | 20 | 21 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 5 | 6,129 | 32,768 | 0 | 792 | 0 | — | `$0.0106` | f1=1.00 |  |
| q00 | on | 4 | 4,990 | 20,096 | 0 | 459 | 6 | — | `$0.0073` | f1=1.00 |  |
| q01 | off | 5 | 6,210 | 32,256 | 0 | 599 | 0 | — | `$0.0098` | f1=0.67 |  |
| q01 | on | 4 | 8,099 | 17,024 | 0 | 641 | 6 | — | `$0.0102` | f1=0.00 |  |

</details>

### `hotpot_opencode_runs/results_gpt4omini.json` — hotpot
agent **opencode** · model **gpt-4o-mini** · family **openai** · sim-rate _OpenAI gpt-4o-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_opencode_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 38,242 | 1,351,270 | +3433.5% |
| · fresh | 3,938 | 1,309,670 | +33157.2% |
| · cache-read | 34,304 | 41,600 | +21.3% |
| · cache-write | 0 | 0 | — |
| output | 409 | 1,255 | +206.8% |
| avg calls/turns | 3.0 | 10.0 | +233.3% |
| ON images (sum) | — | 51 | results |
| ON avg img / call | — | 5.10 | over 10 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0034` | `$0.2003` | +5776.5% |
| F1 (avg) | 1.000 | 0.000 | -100.0% |
| contains (avg) | 1.000 | 0.000 | — |
| avg duration s | 8 | 83 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 3,938 | 34,304 | 0 | 409 | 0 | — | `$0.0034` | f1=1.00 |  |
| q00 | on | 10 | 1,309,670 | 41,600 | 0 | 1,255 | 51 | — | `$0.2003` | f1=0.00 |  |

</details>

### `hotpot_verify_runs/codex/results.json` — hotpot
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (RECON): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_codex_experiment.py@cb64fc3 (defaults: all on)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 38,315 | 24,832 | -35.2% |
| · fresh | 11,179 | 4,736 | -57.6% |
| · cache-read | 27,136 | 20,096 | -25.9% |
| · cache-write | 0 | 0 | — |
| output | 689 | 613 | -11.0% |
| avg calls/turns | 9.0 | 7.0 | -22.2% |
| ON images (sum) | — | 6 | results |
| ON avg img / call | — | 0.86 | over 7 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0135` | `$0.0078` | -42.2% |
| F1 (avg) | 1.000 | 1.000 | +0.0% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 21 | 24 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 9 | 11,179 | 27,136 | 0 | 689 | 0 | — | `$0.0135` | f1=1.00 |  |
| q00 | on | 7 | 4,736 | 20,096 | 0 | 613 | 6 | — | `$0.0078` | f1=1.00 |  |

</details>

### `hotpot_verify_runs/opencode_oauth/results_gpt54mini.json` — hotpot
agent **opencode** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: hotpot_opencode_experiment.py@cb64fc3_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 37,304 | 35,217 | -5.6% |
| · fresh | 37,304 | 35,217 | -5.6% |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 153 | 139 | -9.2% |
| avg calls/turns | 3.0 | 3.0 | +0.0% |
| ON images (sum) | — | 8 | results |
| ON avg img / call | — | 2.67 | over 3 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0287` | `$0.0270` | -5.7% |
| F1 (avg) | 1.000 | 1.000 | +0.0% |
| contains (avg) | 1.000 | 1.000 | — |
| avg duration s | 9 | 15 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 3 | 37,304 | 0 | 0 | 153 | 0 | — | `$0.0287` | f1=1.00 |  |
| q00 | on | 3 | 35,217 | 0 | 0 | 139 | 8 | — | `$0.0270` | f1=1.00 |  |

</details>


# ▶ Benchmark: narrativeqa

### `campaign_20260710_180022/claude_longdoc/results_narrativeqa.json` — narrativeqa
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=0  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 304,987 | 320,168 | +5.0% |
| · fresh | 11,260 | 11,262 | +0.0% |
| · cache-read | 193,320 | 252,379 | +30.5% |
| · cache-write | 100,407 | 56,527 | -43.7% |
| output | 681 | 3,016 | +342.9% |
| avg calls/turns | 2.0 | 2.5 | +25.0% |
| ON images (sum) | — | 30 | ‡events-backfill, shared per-arm log across 2 runs (folder-level, not per-run) |
| ON avg img / call | — | 3.00 | over 10 imaging calls |
| **cost REAL** | `$0.7044` | `$0.4939` | -29.9% |
| **cost SIMULATED** | `$0.4785` | `$0.3667` | -23.4% |
| F1 (avg) | 0.186 | 0.174 | -6.2% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 13 | 38 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 96,656 | 50,885 | 282 | — | `$0.3554` | `$0.2409` | f1=0.21 |  |
| q00 | on | 3 | 5,632 | 155,715 | 28,278 | 779 | — | `$0.2450` | `$0.1813` | f1=0.23 |  |
| q01 | off | 2 | 5,630 | 96,664 | 49,522 | 399 | — | `$0.3490` | `$0.2376` | f1=0.16 |  |
| q01 | on | 2 | 5,630 | 96,664 | 28,249 | 2,237 | — | `$0.2489` | `$0.1854` | f1=0.11 |  |

</details>

### `campaign_dryrun_20260710_152928/claude_longdoc/results_narrativeqa.json` — narrativeqa
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 492,963 | 950,577 | +92.8% |
| · fresh | 11,268 | 11,425 | +1.4% |
| · cache-read | 396,614 | 867,504 | +118.7% |
| · cache-write | 85,081 | 71,648 | -15.8% |
| output | 1,379 | 8,924 | +547.1% |
| avg calls/turns | 4.0 | 7.0 | +75.0% |
| ON images (sum) | — | 84 | ‡events-backfill, shared per-arm log across 2 runs (folder-level, not per-run) |
| ON avg img / call | — | 3.82 | over 22 imaging calls |
| **cost REAL** | `$0.6840` | `$0.8583` | +25.5% |
| **cost SIMULATED** | `$0.4925` | `$0.6971` | +41.5% |
| F1 (avg) | 0.146 | 0.157 | +6.8% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 19 | 92 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 4 | 5,634 | 171,386 | 75,715 | 672 | — | `$0.5327` | `$0.3623` | f1=0.18 |  |
| q00 | on | 11 | 5,793 | 701,595 | 63,068 | 8,517 | — | `$0.7340` | `$0.5921` | f1=0.12 |  |
| q01 | off | 4 | 5,634 | 225,228 | 9,366 | 707 | — | `$0.1513` | `$0.1302` | f1=0.11 |  |
| q01 | on | 3 | 5,632 | 165,909 | 8,580 | 407 | — | `$0.1243` | `$0.1049` | f1=0.19 |  |

</details>

### `claude_nqa_hist0_20260710_182803/results_narrativeqa.json` — narrativeqa
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=0  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 304,987 | 320,168 | +5.0% |
| · fresh | 11,260 | 11,262 | +0.0% |
| · cache-read | 193,320 | 252,379 | +30.5% |
| · cache-write | 100,407 | 56,527 | -43.7% |
| output | 681 | 3,016 | +342.9% |
| avg calls/turns | 2.0 | 2.5 | +25.0% |
| ON images (sum) | — | 24 | events-backfill |
| ON avg img / call | — | 4.80 | over 5 imaging calls |
| **cost REAL** | `$0.7044` | `$0.4939` | -29.9% |
| **cost SIMULATED** | `$0.4785` | `$0.3667` | -23.4% |
| F1 (avg) | 0.186 | 0.174 | -6.2% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 13 | 38 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 96,656 | 50,885 | 282 | — | `$0.3554` | `$0.2409` | f1=0.21 |  |
| q00 | on | 3 | 5,632 | 155,715 | 28,278 | 779 | — | `$0.2450` | `$0.1813` | f1=0.23 |  |
| q01 | off | 2 | 5,630 | 96,664 | 49,522 | 399 | — | `$0.3490` | `$0.2376` | f1=0.16 |  |
| q01 | on | 2 | 5,630 | 96,664 | 28,249 | 2,237 | — | `$0.2489` | `$0.1854` | f1=0.11 |  |

</details>

### `longdoc_claude_runs/results_narrativeqa.json` — narrativeqa
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_claude_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 6 | 6 | +0.0% |
| errors | 0 | 0 | — |
| input total | 893,567 | 753,130 | -15.7% |
| · fresh | 33,782 | 33,780 | -0.0% |
| · cache-read | 640,895 | 582,565 | -9.1% |
| · cache-write | 218,890 | 136,785 | -37.5% |
| output | 1,985 | 4,715 | +137.5% |
| avg calls/turns | 2.2 | 2.0 | -7.7% |
| ON images (sum) | — | 155 | ‡events-backfill, shared per-arm log across 3 runs (folder-level, not per-run) |
| ON avg img / call | — | 5.74 | over 27 imaging calls |
| **cost REAL** | `$1.6367` | `$1.1675` | -28.7% |
| **cost SIMULATED** | `$1.1442` | `$0.8598` | -24.9% |
| F1 (avg) | 0.267 | 0.261 | -2.2% |
| contains (avg) | 0.167 | 0.167 | — |
| avg duration s | 13 | 25 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 2 | 5,630 | 104,816 | 41,087 | 220 | — | `$0.2982` | `$0.2057` | f1=0.27 |  |
| q00 | on | 2 | 5,630 | 104,816 | 18,350 | 468 | — | `$0.1655` | `$0.1242` | f1=0.29 |  |
| q01 | off | 2 | 5,630 | 95,549 | 49,079 | 377 | — | `$0.3457` | `$0.2353` | f1=0.17 |  |
| q01 | on | 2 | 5,630 | 95,549 | 27,746 | 2,627 | — | `$0.2514` | `$0.1890` | f1=0.12 |  |
| q02 | off | 2 | 5,630 | 95,538 | 29,311 | 132 | — | `$0.2234` | `$0.1574` | f1=0.20 |  |
| q02 | on | 2 | 5,630 | 95,538 | 20,036 | 232 | — | `$0.1692` | `$0.1242` | f1=0.20 |  |
| q03 | off | 2 | 5,630 | 95,544 | 28,440 | 159 | — | `$0.2186` | `$0.1546` | f1=0.25 |  |
| q03 | on | 2 | 5,630 | 95,544 | 19,999 | 301 | — | `$0.1701` | `$0.1251` | f1=0.25 |  |
| q04 | off | 2 | 5,630 | 95,558 | 51,404 | 782 | — | `$0.3657` | `$0.2501` | f1=0.04 |  |
| q04 | on | 2 | 5,630 | 95,558 | 27,781 | 479 | — | `$0.2194` | `$0.1569` | f1=0.04 |  |
| q05 | off | 3 | 5,632 | 153,890 | 19,569 | 315 | — | `$0.1852` | `$0.1412` | f1=0.67 |  |
| q05 | on | 2 | 5,630 | 95,560 | 22,873 | 608 | — | `$0.1919` | `$0.1405` | f1=0.67 |  |

</details>

### `longdoc_opencode_runs_gemini_31_flash_lite/results_narrativeqa.json` — narrativeqa
agent **opencode** · model **gemini-3.1-flash-lite** · family **google** · sim-rate _Gemini 3.1 flash-lite approx list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@094debc (junk: provider dropped mid-run)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 3 | 3 | +0.0% |
| errors | 3 | 3 | — |
| input total | 0 | 0 | — |
| · fresh | 0 | 0 | — |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 0 | 0 | — |
| avg calls/turns | 0.0 | 0.0 | — |
| ON images (sum) | — | 0 | results |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0000` | `$0.0000` | — |
| F1 (avg) | 0.000 | 0.000 | — |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 20 | 19 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q00 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q01 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q01 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q02 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q02 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |

</details>

### `campaign_20260710_180022/mimo_longdoc/results_narrativeqa.json` — narrativeqa
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 226,432 | 95,009 | -58.0% |
| · fresh | 62,976 | 16,801 | -73.3% |
| · cache-read | 163,456 | 78,208 | -52.2% |
| · cache-write | 0 | 0 | — |
| output | 982 | 38,614 | +3832.2% |
| avg calls/turns | 4.0 | 4.5 | +12.5% |
| ON images (sum) | — | 80 | results |
| ON avg img / call | — | 8.89 | over 9 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0096` | `$0.0134` | +39.8% |
| F1 (avg) | 0.102 | 0.059 | -41.9% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 19 | 140 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 4 | 31,921 | 81,728 | 0 | 646 | 0 | — | `$0.0049` | f1=0.13 |  |
| q00 | on | 6 | 9,904 | 52,608 | 0 | 4,507 | 52 | — | `$0.0028` | f1=0.12 |  |
| q01 | off | 4 | 31,055 | 81,728 | 0 | 336 | 0 | — | `$0.0047` | f1=0.07 |  |
| q01 | on | 3 | 6,897 | 25,600 | 0 | 34,107 | 28 | — | `$0.0106` | f1=0.00 |  |

</details>

### `campaign_dryrun_20260710_152928/mimo_longdoc/results_narrativeqa.json` — narrativeqa
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 113,774 | 114,692 | +0.8% |
| · fresh | 50,734 | 18,820 | -62.9% |
| · cache-read | 63,040 | 95,872 | +52.1% |
| · cache-write | 0 | 0 | — |
| output | 664 | 6,900 | +939.2% |
| avg calls/turns | 4.5 | 6.0 | +33.3% |
| ON images (sum) | — | 132 | results |
| ON avg img / call | — | 11.00 | over 12 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0075` | `$0.0049` | -35.1% |
| F1 (avg) | 0.158 | 0.077 | -51.3% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 18 | 103 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 7 | 50,734 | 63,040 | 0 | 664 | 0 | — | `$0.0075` | f1=0.32 |  |
| q00 | on | 5 | 6,812 | 25,600 | 0 | 3,519 | 59 | — | `$0.0020` | f1=0.15 |  |
| q01 | off | 2 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 |  |
| q01 | on | 7 | 12,008 | 70,272 | 0 | 3,381 | 73 | — | `$0.0028` | f1=0.00 |  |

</details>

### `longdoc_opencode_runs/results_narrativeqa.json` — narrativeqa
agent **opencode** · model **mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@2327fd7_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 6 | 6 | +0.0% |
| errors | 0 | 0 | — |
| input total | 665,855 | 485,116 | -27.1% |
| · fresh | 162,175 | 52,796 | -67.4% |
| · cache-read | 503,680 | 432,320 | -14.2% |
| · cache-write | 0 | 0 | — |
| output | 4,332 | 13,249 | +205.8% |
| avg calls/turns | 4.0 | 4.0 | +0.0% |
| ON images (sum) | — | 97 | results |
| ON avg img / call | — | 4.04 | over 24 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0254` | `$0.0124` | -51.2% |
| F1 (avg) | 0.294 | 0.212 | -28.0% |
| contains (avg) | 0.167 | 0.167 | — |
| avg duration s | 18 | 44 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 4 | 48,068 | 64,704 | 0 | 585 | 0 | — | `$0.0071` | f1=0.40 |  |
| q00 | on | 3 | 5,295 | 45,312 | 0 | 1,586 | 6 | — | `$0.0013` | f1=0.00 |  |
| q01 | off | 4 | 30,773 | 81,088 | 0 | 294 | 0 | — | `$0.0046` | f1=0.12 |  |
| q01 | on | 3 | 7,445 | 43,392 | 0 | 1,725 | 7 | — | `$0.0017` | f1=0.06 |  |
| q02 | off | 3 | 14,711 | 42,880 | 0 | 135 | 0 | — | `$0.0022` | f1=0.20 |  |
| q02 | on | 6 | 8,811 | 125,312 | 0 | 2,772 | 27 | — | `$0.0024` | f1=0.20 |  |
| q03 | off | 3 | 13,767 | 42,880 | 0 | 243 | 0 | — | `$0.0021` | f1=0.33 |  |
| q03 | on | 3 | 5,834 | 43,392 | 0 | 1,701 | 5 | — | `$0.0014` | f1=0.18 |  |
| q04 | off | 6 | 35,622 | 190,464 | 0 | 2,727 | 0 | — | `$0.0063` | f1=0.04 |  |
| q04 | on | 5 | 12,619 | 103,808 | 0 | 3,102 | 31 | — | `$0.0029` | f1=0.17 |  |
| q05 | off | 4 | 19,234 | 81,664 | 0 | 348 | 0 | — | `$0.0030` | f1=0.67 |  |
| q05 | on | 4 | 12,792 | 71,104 | 0 | 2,363 | 21 | — | `$0.0027` | f1=0.67 |  |

</details>

### `mimo_refix_20260710_160813/mimo_longdoc/results_narrativeqa.json` — narrativeqa
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 340,974 | 138,719 | -59.3% |
| · fresh | 90,926 | 19,487 | -78.6% |
| · cache-read | 250,048 | 119,232 | -52.3% |
| · cache-write | 0 | 0 | — |
| output | 3,810 | 46,900 | +1131.0% |
| avg calls/turns | 9.5 | 14.0 | +47.4% |
| ON images (sum) | — | 272 | results |
| ON avg img / call | — | 9.71 | over 28 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0145` | `$0.0162` | +11.5% |
| F1 (avg) | 0.253 | 0.000 | -100.0% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 44 | 379 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 15 | 61,911 | 166,208 | 0 | 3,394 | 0 | — | `$0.0101` | f1=0.44 |  |
| q00 | on | 10 | 6,919 | 39,296 | 0 | 2,669 | 100 | — | `$0.0018` | f1=0.00 |  |
| q01 | off | 4 | 29,015 | 83,840 | 0 | 416 | 0 | — | `$0.0044` | f1=0.06 |  |
| q01 | on | 18 | 12,568 | 79,936 | 0 | 44,231 | 172 | — | `$0.0144` | f1=0.00 |  |

</details>

### `campaign_20260710_180022/codex_longdoc/results_narrativeqa.json` — narrativeqa
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 107,028 | 107,009 | -0.0% |
| · fresh | 30,868 | 23,937 | -22.5% |
| · cache-read | 76,160 | 83,072 | +9.1% |
| · cache-write | 0 | 0 | — |
| output | 3,209 | 2,695 | -16.0% |
| avg calls/turns | 11.0 | 13.0 | +18.2% |
| ON images (sum) | — | 24 | results |
| ON avg img / call | — | 0.92 | over 26 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0433` | `$0.0363` | -16.1% |
| F1 (avg) | 0.571 | 0.624 | +9.5% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 47 | 46 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 10 | 11,805 | 33,280 | 0 | 1,553 | 0 | — | `$0.0183` | f1=0.20 |  |
| q00 | on | 12 | 14,081 | 36,224 | 0 | 1,294 | 12 | — | `$0.0191` | f1=0.31 |  |
| q01 | off | 12 | 19,063 | 42,880 | 0 | 1,656 | 0 | — | `$0.0250` | f1=0.94 |  |
| q01 | on | 14 | 9,856 | 46,848 | 0 | 1,401 | 12 | — | `$0.0172` | f1=0.94 |  |

</details>

### `campaign_dryrun_20260710_152928/codex_longdoc/results_narrativeqa.json` — narrativeqa
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 110,065 | 70,480 | -36.0% |
| · fresh | 19,697 | 22,224 | +12.8% |
| · cache-read | 90,368 | 48,256 | -46.6% |
| · cache-write | 0 | 0 | — |
| output | 2,721 | 1,968 | -27.7% |
| avg calls/turns | 6.0 | 4.5 | -25.0% |
| ON images (sum) | — | 16 | results |
| ON avg img / call | — | 1.78 | over 9 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0338` | `$0.0291` | -13.8% |
| F1 (avg) | 0.461 | 0.521 | +13.0% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 41 | 33 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 7 | 12,465 | 54,016 | 0 | 1,539 | 0 | — | `$0.0203` | f1=0.22 |  |
| q00 | on | 5 | 11,711 | 27,648 | 0 | 907 | 10 | — | `$0.0149` | f1=0.17 |  |
| q01 | off | 5 | 7,232 | 36,352 | 0 | 1,182 | 0 | — | `$0.0135` | f1=0.70 |  |
| q01 | on | 4 | 10,513 | 20,608 | 0 | 1,061 | 6 | — | `$0.0142` | f1=0.88 |  |

</details>

### `longdoc_opencode_runs/results_narrativeqa_gpt4omini.json` — narrativeqa
agent **opencode** · model **gpt-4o-mini** · family **openai** · sim-rate _OpenAI gpt-4o-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@2327fd7_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 1 | 1 | — |
| input total | 0 | 0 | — |
| · fresh | 0 | 0 | — |
| · cache-read | 0 | 0 | — |
| · cache-write | 0 | 0 | — |
| output | 0 | 0 | — |
| avg calls/turns | 0.0 | 0.0 | — |
| ON images (sum) | — | 0 | results |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0000` | `$0.0000` | — |
| F1 (avg) | 0.000 | 0.000 | — |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 13 | 13 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |
| q00 | on | 0 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | f1=0.00 | Y |

</details>

### `longdoc_opencode_runs_gpt_54_mini/results_narrativeqa.json` — narrativeqa
agent **opencode** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (RECON): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: longdoc_opencode_experiment.py@162ccbe_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 1 | 1 | +0.0% |
| errors | 0 | 0 | — |
| input total | 82,327 | 178,226 | +116.5% |
| · fresh | 47,511 | 170,546 | +259.0% |
| · cache-read | 34,816 | 7,680 | -77.9% |
| · cache-write | 0 | 0 | — |
| output | 520 | 2,419 | +365.2% |
| avg calls/turns | 4.0 | 8.0 | +100.0% |
| ON images (sum) | — | 44 | results |
| ON avg img / call | — | 5.50 | over 8 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0406` | `$0.1394` | +243.4% |
| F1 (avg) | 0.182 | 0.000 | -100.0% |
| contains (avg) | 0.000 | 0.000 | — |
| avg duration s | 17 | 99 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| q00 | off | 4 | 47,511 | 34,816 | 0 | 520 | 0 | — | `$0.0406` | f1=0.18 |  |
| q00 | on | 8 | 170,546 | 7,680 | 0 | 2,419 | 44 | — | `$0.1394` | f1=0.00 |  |

</details>


# ▶ Benchmark: swebench

### `campaign_20260710_180022/claude_swebench/results.json` — swebench
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=0 · HIST=0  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 538,661 | 542,308 | +0.7% |
| · fresh | 11,268 | 11,268 | +0.0% |
| · cache-read | 449,231 | 494,720 | +10.1% |
| · cache-write | 78,162 | 36,320 | -53.5% |
| output | 1,594 | 1,319 | -17.3% |
| avg calls/turns | 4.5 | 4.5 | +0.0% |
| ON images (sum) | — | 0 | events-backfill |
| ON avg img / call | — | 0.00 | over 9 imaging calls |
| **cost REAL** | `$0.6615` | `$0.4199` | -36.5% |
| **cost SIMULATED** | `$0.4856` | `$0.3382` | -30.4% |
| avg duration s | 22 | 21 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 5 | 5,635 | 235,527 | 62,194 | 1,046 | — | `$0.4764` | `$0.3365` | — |  |
| psf__requests-1963 | on | 4 | 5,633 | 217,093 | 17,942 | 796 | — | `$0.2016` | `$0.1612` | — |  |
| pallets__flask-4045 | off | 4 | 5,633 | 213,704 | 15,968 | 548 | — | `$0.1850` | `$0.1491` | — |  |
| pallets__flask-4045 | on | 5 | 5,635 | 277,627 | 18,378 | 523 | — | `$0.2183` | `$0.1770` | — |  |

</details>

### `campaign_dryrun_20260710_152928/claude_swebench/results.json` — swebench
agent **claude** · model **sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (DATA): SYS=0 · TOOLS=0 · TOOL_RES=1 · USER=0 · HIST=0  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 661,004 | 479,186 | -27.5% |
| · fresh | 11,272 | 11,266 | -0.1% |
| · cache-read | 612,295 | 432,755 | -29.3% |
| · cache-write | 37,437 | 35,165 | -6.1% |
| output | 2,180 | 1,831 | -16.0% |
| avg calls/turns | 5.5 | 4.0 | -27.3% |
| ON images (sum) | — | 0 | events-backfill |
| ON avg img / call | — | 0.00 | over 8 imaging calls |
| **cost REAL** | `$0.4748` | `$0.4021` | -15.3% |
| **cost SIMULATED** | `$0.3906` | `$0.3230` | -17.3% |
| avg duration s | 25 | 23 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 4 | 5,633 | 215,693 | 17,639 | 914 | — | `$0.2012` | `$0.1615` | — |  |
| psf__requests-1963 | on | 4 | 5,633 | 217,156 | 17,990 | 952 | — | `$0.2043` | `$0.1638` | — |  |
| pallets__flask-4045 | off | 7 | 5,639 | 396,602 | 19,798 | 1,266 | — | `$0.2737` | `$0.2291` | — |  |
| pallets__flask-4045 | on | 4 | 5,633 | 215,599 | 17,175 | 879 | — | `$0.1978` | `$0.1592` | — |  |

</details>

### `swebench_claude_runs/results.json` — swebench
agent **claude** · model **claude-sonnet** · family **anthropic** · sim-rate _Anthropic claude-sonnet list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: swebench_claude_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 0 | — |
| input total | 1,627,877 | 1,225,093 | -24.7% |
| · fresh | 28,324 | 28,332 | +0.0% |
| · cache-read | 1,507,573 | 1,024,189 | -32.1% |
| · cache-write | 91,980 | 172,572 | +87.6% |
| output | 7,314 | 5,937 | -18.8% |
| avg calls/turns | 5.4 | 6.4 | +18.5% |
| ON images (sum) | — | 420 | events-backfill |
| ON avg img / call | — | 13.55 | over 31 imaging calls |
| **cost REAL** | `$1.1988` | `$1.5167` | +26.5% |
| **cost SIMULATED** | `$0.9919` | `$1.1285` | +13.8% |
| avg duration s | 28 | 78 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 4 | 5,633 | 215,066 | 17,525 | 880 | — | `$0.1998` | `$0.1603` | — |  |
| psf__requests-1963 | on | 5 | 5,635 | 160,124 | 32,783 | 860 | — | `$0.2745` | `$0.2008` | — |  |
| pallets__flask-4045 | off | 4 | 5,633 | 213,195 | 16,841 | 742 | — | `$0.1930` | `$0.1551` | — |  |
| pallets__flask-4045 | on | 4 | 5,633 | 117,243 | 31,125 | 654 | — | `$0.2486` | `$0.1786` | — |  |
| pylint-dev__pylint-585 | off | 6 | 5,637 | 335,304 | 18,588 | 2,505 | — | `$0.2666` | `$0.2248` | — |  |
| pylint-dev__pylint-585 | on | 4 | 5,633 | 116,868 | 30,785 | 881 | — | `$0.2499` | `$0.1806` | — |  |
| pytest-dev__pytest-111 | off | 4 | 5,633 | 220,269 | 19,101 | 1,162 | — | `$0.2150` | `$0.1720` | — |  |
| pytest-dev__pytest-111 | on | 6 | 5,637 | 207,243 | 34,179 | 1,494 | — | `$0.3066` | `$0.2297` | — |  |
| psf__requests-2148 | off | 9 | 5,788 | 523,739 | 19,925 | 2,025 | — | `$0.3244` | `$0.2796` | — |  |
| psf__requests-2148 | on | 13 | 5,794 | 422,711 | 43,700 | 2,048 | — | `$0.4371` | `$0.3388` | — |  |

</details>

### `swebench_opencode_runs_gemini_31_flash_lite/results.json` — swebench
agent **opencode** · model **gemini-3.1-flash-lite** · family **google** · sim-rate _Gemini 3.1 flash-lite approx list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: swebench_opencode_experiment.py@094debc_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 1 | — |
| input total | 305,361 | 581,581 | +90.5% |
| · fresh | 215,809 | 390,516 | +81.0% |
| · cache-read | 89,552 | 191,065 | +113.4% |
| · cache-write | 0 | 0 | — |
| output | 1,053 | 1,375 | +30.6% |
| avg calls/turns | 6.5 | 10.5 | +61.5% |
| ON images (sum) | — | 213 | results |
| ON avg img / call | — | 10.14 | over 21 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0242` | `$0.0444` | +83.1% |
| patches produced | 2/2 | 2/2 | — |
| avg duration s | 30 | 247 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 8 | 172,866 | 28,516 | 0 | 748 | 0 | — | `$0.0183` | patch |  |
| psf__requests-1963 | on | 15 | 369,963 | 93,592 | 0 | 1,101 | 184 | — | `$0.0398` | patch | Y |
| pallets__flask-4045 | off | 5 | 42,943 | 61,036 | 0 | 305 | 0 | — | `$0.0059` | patch |  |
| pallets__flask-4045 | on | 6 | 20,553 | 97,473 | 0 | 274 | 29 | — | `$0.0046` | patch |  |

</details>

### `campaign_20260710_180022/mimo_swebench/results.json` — swebench
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 1 | — |
| input total | 1,772,755 | 655,714 | -63.0% |
| · fresh | 68,115 | 137,506 | +101.9% |
| · cache-read | 1,704,640 | 518,208 | -69.6% |
| · cache-write | 0 | 0 | — |
| output | 20,711 | 7,682 | -62.9% |
| avg calls/turns | 28.5 | 19.5 | -31.6% |
| ON images (sum) | — | 564 | results |
| ON avg img / call | — | 14.46 | over 39 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0204` | `$0.0230` | +12.3% |
| patches produced | 2/2 | 2/2 | — |
| avg duration s | 186 | 353 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 12 | 14,431 | 299,200 | 0 | 5,527 | 0 | — | `$0.0045` | patch |  |
| psf__requests-1963 | on | 8 | 8,463 | 95,232 | 0 | 1,175 | 74 | — | `$0.0018` | patch |  |
| pallets__flask-4045 | off | 45 | 53,684 | 1,405,440 | 0 | 15,184 | 0 | — | `$0.0160` | patch |  |
| pallets__flask-4045 | on | 31 | 129,043 | 422,976 | 0 | 6,507 | 490 | — | `$0.0212` | patch | Y |

</details>

### `campaign_dryrun_20260710_152928/mimo_swebench/results.json` — swebench
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 2 | — |
| input total | 1,297,275 | 476,090 | -63.3% |
| · fresh | 95,547 | 100,474 | +5.2% |
| · cache-read | 1,201,728 | 375,616 | -68.7% |
| · cache-write | 0 | 0 | — |
| output | 19,776 | 11,530 | -41.7% |
| avg calls/turns | 35.0 | 24.5 | -30.0% |
| ON images (sum) | — | 573 | results |
| ON avg img / call | — | 11.69 | over 49 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0225` | `$0.0184` | -18.2% |
| patches produced | 2/2 | — | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 14 | 4,681 | 185,216 | 0 | 4,356 | 0 | — | `$0.0024` | patch |  |
| psf__requests-1963 | on | 20 | 36,531 | 155,264 | 0 | 3,830 | 235 | — | `$0.0067` | — | Y |
| pallets__flask-4045 | off | 56 | 90,866 | 1,016,512 | 0 | 15,420 | 0 | — | `$0.0201` | patch |  |
| pallets__flask-4045 | on | 29 | 63,943 | 220,352 | 0 | 7,700 | 338 | — | `$0.0118` | — | Y |

</details>

### `mimo_refix_20260710_160813/mimo_swebench/results.json` — swebench
agent **mimo** · model **opencode/mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 2 | 1 | — |
| input total | 176,130 | 280,026 | +59.0% |
| · fresh | 3,970 | 32,922 | +729.3% |
| · cache-read | 172,160 | 247,104 | +43.5% |
| · cache-write | 0 | 0 | — |
| output | 1,165 | 2,863 | +145.8% |
| avg calls/turns | 17.5 | 24.5 | +40.0% |
| ON images (sum) | — | 455 | results |
| ON avg img / call | — | 9.29 | over 49 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0014` | `$0.0062` | +339.9% |
| patches produced | 1/1 | 2/2 | — |
| avg duration s | 30 | 392 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 27 | 3,970 | 172,160 | 0 | 1,165 | 0 | — | `$0.0014` | — | Y |
| psf__requests-1963 | on | 41 | 32,922 | 247,104 | 0 | 2,863 | 411 | — | `$0.0062` | patch |  |
| pallets__flask-4045 | off | 8 | 0 | 0 | 0 | 0 | 0 | — | `$0.0000` | patch | Y |
| pallets__flask-4045 | on | 8 | 0 | 0 | 0 | 0 | 44 | — | `$0.0000` | patch | Y |

</details>

### `swebench_opencode_runs/results.json` — swebench
agent **opencode** · model **mimo-v2.5-free** · family **mimo** · sim-rate _Xiaomi MiMo-V2.5 first-party list_
ON imaging regions (RECON): SYS=0 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: swebench_opencode_experiment.py@2327fd7_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 5 | 5 | +0.0% |
| errors | 0 | 1 | — |
| input total | 2,054,039 | 1,464,868 | -28.7% |
| · fresh | 134,679 | 245,860 | +82.6% |
| · cache-read | 1,919,360 | 1,219,008 | -36.5% |
| · cache-write | 0 | 0 | — |
| output | 27,902 | 51,588 | +84.9% |
| avg calls/turns | 15.0 | 13.4 | -10.7% |
| ON images (sum) | — | 585 | results |
| ON avg img / call | — | 8.73 | over 67 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0324` | `$0.0525` | +62.0% |
| patches produced | 3/5 | 1/4 | — |
| avg duration s | 87 | 186 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 12 | 16,928 | 298,624 | 0 | 4,350 | 0 | — | `$0.0045` | no-patch |  |
| psf__requests-1963 | on | 14 | 71,437 | 249,216 | 0 | 5,119 | 120 | — | `$0.0122` | patch |  |
| pallets__flask-4045 | off | 18 | 74,765 | 386,624 | 0 | 6,447 | 0 | — | `$0.0134` | patch |  |
| pallets__flask-4045 | on | 10 | 28,710 | 168,512 | 0 | 2,163 | 94 | — | `$0.0051` | no-patch |  |
| pylint-dev__pylint-585 | off | 13 | 12,080 | 329,856 | 0 | 6,535 | 0 | — | `$0.0045` | patch |  |
| pylint-dev__pylint-585 | on | 30 | 111,335 | 562,048 | 0 | 6,598 | 284 | — | `$0.0191` | — | Y |
| pytest-dev__pytest-111 | off | 8 | 9,627 | 174,400 | 0 | 3,694 | 0 | — | `$0.0029` | patch |  |
| pytest-dev__pytest-111 | on | 5 | 6,494 | 84,288 | 0 | 2,444 | 20 | — | `$0.0018` | no-patch |  |
| psf__requests-2148 | off | 24 | 21,279 | 729,856 | 0 | 6,876 | 0 | — | `$0.0071` | no-patch |  |
| psf__requests-2148 | on | 8 | 27,884 | 154,944 | 0 | 35,264 | 67 | — | `$0.0142` | no-patch |  |

</details>

### `campaign_20260710_180022/codex_swebench/results.json` — swebench
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 95,453 | 77,343 | -19.0% |
| · fresh | 17,245 | 11,423 | -33.8% |
| · cache-read | 78,208 | 65,920 | -15.7% |
| · cache-write | 0 | 0 | — |
| output | 4,843 | 2,595 | -46.4% |
| avg calls/turns | 11.0 | 11.0 | +0.0% |
| ON images (sum) | — | 18 | results |
| ON avg img / call | — | 0.82 | over 22 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0406` | `$0.0252` | -37.9% |
| patches produced | 2/2 | 2/2 | — |
| avg duration s | 55 | 41 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 10 | 6,211 | 34,304 | 0 | 2,702 | 0 | — | `$0.0194` | patch |  |
| psf__requests-1963 | on | 12 | 5,929 | 38,272 | 0 | 1,573 | 10 | — | `$0.0144` | patch |  |
| pallets__flask-4045 | off | 12 | 11,034 | 43,904 | 0 | 2,141 | 0 | — | `$0.0212` | patch |  |
| pallets__flask-4045 | on | 10 | 5,494 | 27,648 | 0 | 1,022 | 8 | — | `$0.0108` | patch |  |

</details>

### `campaign_dryrun_20260710_152928/codex_swebench/results.json` — swebench
agent **codex** · model **gpt-5.4-mini** · family **openai** · sim-rate _OpenAI gpt-5.4-mini list_
ON imaging regions (DATA): SYS=1 · TOOLS=1 · TOOL_RES=1 · USER=1 · HIST=1  
_config source: run_meta.on_env (recorded at run time)_ · OFF arm images nothing (IMGCTX_ENABLED=0)

| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| items | 2 | 2 | +0.0% |
| errors | 0 | 0 | — |
| input total | 111,704 | 78,363 | -29.8% |
| · fresh | 10,200 | 7,835 | -23.2% |
| · cache-read | 101,504 | 70,528 | -30.5% |
| · cache-write | 0 | 0 | — |
| output | 3,770 | 3,549 | -5.9% |
| avg calls/turns | 6.5 | 5.5 | -15.4% |
| ON images (sum) | — | 18 | results |
| ON avg img / call | — | 1.64 | over 11 imaging calls |
| **cost REAL** | — | — | — |
| **cost SIMULATED** | `$0.0322` | `$0.0271` | -15.8% |
| patches produced | 1/2 | 1/2 | — |
| avg duration s | 45 | 49 | — |

<details><summary>per-item detail</summary>

| item | cond | calls | fresh | c-read | c-write | out | imgs | real USD | sim USD | score | err |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--:|
| psf__requests-1963 | off | 8 | 7,475 | 65,152 | 0 | 2,218 | 0 | — | `$0.0205` | patch |  |
| psf__requests-1963 | on | 6 | 4,438 | 40,832 | 0 | 2,500 | 10 | — | `$0.0176` | patch |  |
| pallets__flask-4045 | off | 5 | 2,725 | 36,352 | 0 | 1,552 | 0 | — | `$0.0118` | no-patch |  |
| pallets__flask-4045 | on | 5 | 3,397 | 29,696 | 0 | 1,049 | 8 | — | `$0.0095` | no-patch |  |

</details>
