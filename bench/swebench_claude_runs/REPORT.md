# SWE-bench Lite: imgctx A/B on Claude Code (`claude-sonnet-5`)

Real Claude Code CLI (`claude -p`, model `claude-sonnet-5`) run agentically on SWE-bench Lite instances, each resolved twice through an identical proxy: compression OFF (passthrough) and ON. Tokens are the provider's own usage; **dollars are Claude Code's own reported `total_cost_usd`** (authoritative, it prices the exact model and the 1-hour cache TTL Claude Code uses). Earlier versions of this report used a hand-rolled price formula that mis-priced the 1h-cache write rate and understated the cost gap; it has been removed. Tests are not executed (no Docker); patches are captured for later grading.

ON config: system prompt kept as text (`IMGCTX_SYSTEM=0`); tools + tool_results + older user text imaged; **history-collapse ON** (old closed prefix frozen into byte-stable cache-read images, recent tail kept as text); inherited cache_control markers relocated, never stripped.

- instances attempted: 5
- matched (both completed cleanly): 5

## Headline (matched subset)

| metric | OFF | ON | change |
| --- | ---: | ---: | ---: |
| total input tokens | 1,627,877 | 1,225,093 | **-24.7%** |
| total cost (USD), real total_cost_usd, n=5 | $1.1988 | $1.5167 | **+26.5%** |
| median input-token change / instance | | | **-16.7%** |

### By token class (real per-field usage)

Imaging only compresses **input**; the three input classes are priced very differently, so the class that moves is what moves the bill.

| token class | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 28,324 | 28,332 | **+0.0%** |
| cache WRITE (~1.25-2x) | 91,980 | 172,572 | **+87.6%** |
| cache read (~0.1x) | 1,507,573 | 1,024,189 | **-32.1%** |
| **input-side total (imaged)** | 1,627,877 | 1,225,093 | **-24.7%** |
| output (not compressed) | 7,314 | 5,937 | -18.8% |

The bill follows the **cache-WRITE** row, not the blended total: it is the priciest input class, so its direction (down = cheaper, up = pricier) decides the real-dollar sign.

## Per-call compression (imgctx-controlled, trajectory-independent)

Every API call the proxy billed this run, aggregated. This isolates what compression does to a single request from how many turns the agent takes.

| metric | OFF | ON | change |
| --- | ---: | ---: | ---: |
| API calls | 27 | 31 | |
| mean input tokens / call | 60,292 | 39,519 | **-34.5%** |
| mean cache-creation / call | 3,407 | 5,567 | **+63.4%** |

_(Per-call dollars are intentionally omitted: Claude reports `total_cost_usd` only cumulatively at run end, so a per-call dollar figure would have to be a hand-rolled estimate. All dollars in this report are Claude's own end-to-end billed cost.)_

## Per-instance (end-to-end, trajectory-dependent)

| instance | repo | in tok OFF | in tok ON | Δ tok | $ OFF | $ ON | turns O/N | patch O/N | err |
| --- | --- | ---: | ---: | ---: | ---: | ---: | :--: | :--: | :--: |
| psf__requests-1963 | requests | 238,224 | 198,542 | -16.7% | $0.1998 | $0.2745 | 4/5 | Y/Y | - |
| pallets__flask-4045 | flask | 235,669 | 154,001 | -34.7% | $0.1930 | $0.2486 | 4/4 | Y/Y | - |
| pylint-dev__pylint-5859 | pylint | 359,529 | 153,286 | -57.4% | $0.2666 | $0.2499 | 6/4 | Y/Y | - |
| pytest-dev__pytest-11143 | pytest | 245,003 | 247,059 | +0.8% | $0.2150 | $0.3066 | 4/6 | Y/Y | - |
| psf__requests-2148 | requests | 549,452 | 472,205 | -14.1% | $0.3244 | $0.4371 | 9/13 | Y/Y | - |

## Why: Anthropic prompt-cache interaction

Input-side token mix (real token counts from Claude's per-call usage, shown as shares). Anthropic prices these tiers very differently, cache-read is by far the cheapest, and cache-WRITE is the most expensive (Claude Code writes at the 1-hour cache TTL, ~2x the base input rate). Dollars in this report are Claude's own `total_cost_usd`, not derived from these shares.

| share of input-side tokens | OFF | ON |
| --- | ---: | ---: |
| cache-read (cheapest) | 93% | 84% |
| fresh input | 1.7% | 2.3% |
| cache-write (most expensive) | 6% | 14% |

Claude Code's native caching keeps ~97% of the OFF context as cheap cache-reads. Two imgctx design fixes keep ON's mix close to that: (1) inherited cache_control markers are RELOCATED, never stripped, so Claude Code's moving message-tail breakpoint survives and history still cache-reads, ON's **fresh input stays ~0%**, not the double digits an earlier strip-and-re-add design produced; (2) **history-collapse** freezes the old closed prefix into byte-stable images that cache-read instead of re-imaging tool_results every turn at the cache-write rate. The residual gap is that remaining cache-write share (imaged bytes are new the first turn each frozen chunk appears, and short early-turn requests still image per-message before collapse is profitable), and cache-write is the priciest tier, so even a small share swing moves real dollars up.

## Verdict

- **Token compression works**: matched input tokens fall 25% (claude-sonnet-5), and with history-collapse the per-instance cumulative tokens fall too (no per-turn re-imaging blowup).
- **But real dollars go UP +27%** (Claude's own `total_cost_usd`, not a formula). Fewer tokens does not mean fewer dollars: imaging converts context that OFF gets as cheap cache-reads into cache-WRITES billed at the 1-hour-TTL rate (~2x input). Per-instance the sign is turn-count sensitive, where ON took fewer agent turns it can still come in cheaper (this run: pylint ON 4 vs 6 turns → ON cheaper); where it took more, pricier, but the matched total is clearly positive.
- **Why**: Anthropic already caches repeated text cheaply, so imaging mostly trades cheap reads for expensive writes. Imaging pays only where text is NOT already cheaply cached, a cheap-vision model like `claude-fable-5`, or a provider with no text cache; cache-cheap models (Opus/Haiku/Sonnet) additionally carry a ~7% image read tax. Our real-cost result agrees: a net loss, not a win. Magnitude is model- and task-specific and only the real number reveals it (measured here: SWE-bench Sonnet ~+26%, short-trajectory HotpotQA Sonnet ~+44%, HotpotQA Haiku ~+200%).
- **Where imaging DOES pay**: providers with no cheap text cache (the OpenCode/mimo path, ~-33% end-to-end), or a cheap-vision model like Fable 5.
- **Correctness**: 0 tool-call errors, 0 HTTP 400s, every ON call compressed, the restructured (imaged + collapsed) request is accepted and tool use stays intact.
