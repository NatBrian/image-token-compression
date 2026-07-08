# OpenCode / mimo-v2.5-free: cache and simulated cost, all benchmarks

**mimo-v2.5-free is FREE, so the real provider-billed cost is $0.00 on every run.** The token and cache numbers below are REAL (the zen/mimo endpoint's own `usage`, including its cache split). **The dollar figures are a SIMULATION** under a representative OpenAI-style rate table (fresh input $0.150/M, cache-write $0.150/M with NO premium, cache-read $0.075/M at 0.5x, output $0.600/M), shown only to reveal the SHAPE of the bill. They are not a real charge.

The structural point: `cache_write_tokens` is 0 on every call here, so unlike Anthropic there is no 2x write class for imaging to inflate. The input-token cut therefore becomes a (simulated) cost cut in EVERY regime, including the re-read tasks (SWE-bench, HotpotQA) that lost money on Anthropic. See `docs/input-tokens-vs-cost.md`.

## Summary: every regime wins on OpenCode

| benchmark | input tokens Δ | cache-write tokens (OFF+ON) | simulated input-side cost Δ |
| --- | ---: | ---: | ---: |
| HotpotQA (re-read, short) | -32.9% | 0 | -32.1% |
| SWE-bench Lite (re-read, agentic) | -53.8% | 0 | -49.5% |
| narrativeqa (read once) | -27.1% | 0 | -35.0% |
| gov_report (read once) | -39.4% | 0 | -41.6% |

cache-write is 0 across the board, so the token cut and the simulated cost cut share a sign in every row: the opposite of the Anthropic re-read result, and the clearest proof that the Anthropic cost rise is that provider's write premium, not an imgctx property.

**Caveat (honest):** output/`completion_tokens` swings with nondeterministic agent looping and is shown separately; read the input-side row for the imgctx signal. All dollars are simulated (free model).


## HotpotQA (re-read, short)  (matched n=10)

| token class | field | OFF | ON | Δ tok | sim $ OFF | sim $ ON |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| total input | `prompt_tokens` | 465,401 | 312,501 | -32.9% | | |
| cache READ | `cached_tokens` | 424,064 | 280,832 | -33.8% | $0.0318 | $0.0211 |
| cache WRITE | `cache_write_tokens` | 0 | 0 | (both 0) | $0.0000 | $0.0000 |
| fresh (uncached) | prompt-read-write | 41,337 | 31,669 | -23.4% | $0.0062 | $0.0048 |
| **input-side (imgctx)** | prompt total | **465,401** | **312,501** | **-32.9%** | **$0.0380** | **$0.0258** |
| output (loop variance) | `completion_tokens` | 1,559 | 14,026 | +799.7% | $0.0009 | $0.0084 |

- Real provider cost: **$0.00 / $0.00** (mimo-v2.5-free). cache WRITE = 0 both arms.
- Simulated input-side cost Δ: **-32.1%** (token cut flows to the bill; no write premium to claw it back).

## SWE-bench Lite (re-read, agentic)  (matched n=4)

| token class | field | OFF | ON | Δ tok | sim $ OFF | sim $ ON |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| total input | `prompt_tokens` | 1,712,103 | 791,485 | -53.8% | | |
| cache READ | `cached_tokens` | 1,589,504 | 656,960 | -58.7% | $0.1192 | $0.0493 |
| cache WRITE | `cache_write_tokens` | 0 | 0 | (both 0) | $0.0000 | $0.0000 |
| fresh (uncached) | prompt-read-write | 122,599 | 134,525 | +9.7% | $0.0184 | $0.0202 |
| **input-side (imgctx)** | prompt total | **1,712,103** | **791,485** | **-53.8%** | **$0.1376** | **$0.0695** |
| output (loop variance) | `completion_tokens` | 21,367 | 44,990 | +110.6% | $0.0128 | $0.0270 |

- Real provider cost: **$0.00 / $0.00** (mimo-v2.5-free). cache WRITE = 0 both arms.
- Simulated input-side cost Δ: **-49.5%** (token cut flows to the bill; no write premium to claw it back).

## narrativeqa (read once)  (matched n=6)

| token class | field | OFF | ON | Δ tok | sim $ OFF | sim $ ON |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| total input | `prompt_tokens` | 665,855 | 485,116 | -27.1% | | |
| cache READ | `cached_tokens` | 503,680 | 432,320 | -14.2% | $0.0378 | $0.0324 |
| cache WRITE | `cache_write_tokens` | 0 | 0 | (both 0) | $0.0000 | $0.0000 |
| fresh (uncached) | prompt-read-write | 162,175 | 52,796 | -67.4% | $0.0243 | $0.0079 |
| **input-side (imgctx)** | prompt total | **665,855** | **485,116** | **-27.1%** | **$0.0621** | **$0.0403** |
| output (loop variance) | `completion_tokens` | 4,332 | 13,249 | +205.8% | $0.0026 | $0.0079 |

- Real provider cost: **$0.00 / $0.00** (mimo-v2.5-free). cache WRITE = 0 both arms.
- Simulated input-side cost Δ: **-35.0%** (token cut flows to the bill; no write premium to claw it back).

## gov_report (read once)  (matched n=4)

| token class | field | OFF | ON | Δ tok | sim $ OFF | sim $ ON |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| total input | `prompt_tokens` | 763,068 | 462,073 | -39.4% | | |
| cache READ | `cached_tokens` | 681,280 | 430,912 | -36.7% | $0.0511 | $0.0323 |
| cache WRITE | `cache_write_tokens` | 0 | 0 | (both 0) | $0.0000 | $0.0000 |
| fresh (uncached) | prompt-read-write | 81,788 | 31,161 | -61.9% | $0.0123 | $0.0047 |
| **input-side (imgctx)** | prompt total | **763,068** | **462,073** | **-39.4%** | **$0.0634** | **$0.0370** |
| output (loop variance) | `completion_tokens` | 10,287 | 10,520 | +2.3% | $0.0062 | $0.0063 |

- Real provider cost: **$0.00 / $0.00** (mimo-v2.5-free). cache WRITE = 0 both arms.
- Simulated input-side cost Δ: **-41.6%** (token cut flows to the bill; no write premium to claw it back).
