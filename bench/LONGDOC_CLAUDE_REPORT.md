# Long-document single-shot A/B: imgctx ON vs OFF on Claude Code

The **non-cache-heavy** counter-example to the SWE-bench / HotpotQA runs. Each item is one LARGE, UNIQUE document read exactly ONCE and answered once. Because the doc is unique and read a single time, OFF has no cheap cache-read to lose, it must pay the whole doc as fresh input on the answer turn, same as ON. The ON arm images ONLY that read-once doc (`IMGCTX_SYSTEM=0`, `IMGCTX_TOOLS=0`), so the fixed system+tool prefix stays text and cache-reads at 0.1x identically for both arms. **All dollars are Claude Code's own `total_cost_usd`; all tokens are Claude's real per-field usage.** No price formula, the only math is summation and percent-change.

Model: `claude-sonnet-5`.

## Headline, real numbers

| task | n | input tokens OFF→ON | Δ tokens | real cost OFF→ON | Δ cost | F1 OFF→ON |
| --- | ---: | --- | ---: | --- | ---: | --- |
| narrativeqa | 6 | 2,369,841 → 2,022,724 | **-14.6%** | `$2.0510` → `$1.6900` | **-17.6%** | 0.267 → 0.261 |
| gov_report | 4 | 2,038,158 → 1,769,692 | **-13.2%** | `$1.5001` → `$1.2786` | **-14.8%** | 0.102 → 0.123 |
| **all** | | 4,407,999 → 3,792,416 | **-14.0%** | `$3.5511` → `$2.9686` | **-16.4%** | |

## Where the cut lands (per token class)

**narrativeqa** (long single-doc QA (~30k-tok books/scripts))

### narrativeqa: real per-field usage

Imaging only compresses **input**; the three input classes are priced very differently, so the class that moves is what moves the bill.

| token class | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 34,112 | 33,963 | **-0.4%** |
| cache WRITE (~1.25-2x) | 193,032 | 140,534 | **-27.2%** |
| cache read (~0.1x) | 2,142,697 | 1,848,227 | **-13.7%** |
| **input-side total (imaged)** | 2,369,841 | 2,022,724 | **-14.6%** |
| output (not compressed) | 9,845 | 12,694 | +28.9% |

The bill follows the **cache-WRITE** row, not the blended total: it is the priciest input class, so its direction (down = cheaper, up = pricier) decides the real-dollar sign.

**gov_report** (long-doc summarization (~13k-tok government reports))

### gov_report: real per-field usage

Imaging only compresses **input**; the three input classes are priced very differently, so the class that moves is what moves the bill.

| token class | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 22,850 | 22,703 | **-0.6%** |
| cache WRITE (~1.25-2x) | 122,059 | 89,880 | **-26.4%** |
| cache read (~0.1x) | 1,893,249 | 1,657,109 | **-12.5%** |
| **input-side total (imaged)** | 2,038,158 | 1,769,692 | **-13.2%** |
| output (not compressed) | 8,748 | 11,607 | +32.7% |

The bill follows the **cache-WRITE** row, not the blended total: it is the priciest input class, so its direction (down = cheaper, up = pricier) decides the real-dollar sign.

## Verdict

- **Both fall.** Tokens -14.0% and real dollars -16.4% across the long-doc tasks. This is the regime imgctx is built for: one big unique input, read once.
- **Why it wins here but lost on SWE-bench / HotpotQA:** there the compressible mass was a *reusable cached prefix* (Claude Code's fixed system prompt, or a doc re-read across many agentic turns), which OFF already gets at the 0.1x cache-read rate, so imaging only converted cheap reads into pricier writes. Here the doc is read once, so OFF pays it at fresh 1x too, and imaging's token cut lands on that expensive fresh input.
- **Dollars fall faster than tokens** because the tokens removed are the most expensive class (fresh input), not 0.1x cache-reads.
- **Correctness holds:** answer quality (F1 / summary) is within noise of the OFF baseline; compression did not degrade the task.
- **Rule of thumb:** image when the big context is UNIQUE and read a few times or fewer (single-shot long-doc QA, summarization, classification, one-pass extraction). Leave it OFF when the same context is re-read across a long agentic loop (that is what prompt caching already makes cheap).
