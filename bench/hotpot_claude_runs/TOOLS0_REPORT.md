# HotpotQA `IMGCTX_TOOLS=0` rerun: isolating config from task shape

**Question this run answers:** the headline benchmarks mixed *task shape* (re-read vs read-once) with *config* (whether imgctx imaged the warm tool prefix). Did HotpotQA's cost loss come from the task, or from imaging a region Anthropic was already caching cheaply?

**Setup:** real Claude Code CLI (`claude -p`, `claude-sonnet-5`), n=5, same questions, each run twice (OFF passthrough vs ON). The only change from the baseline is the ON arm's config. All tokens are Claude's real per-field usage; all dollars are Claude Code's own `total_cost_usd`. No price formula.

| arm | `IMGCTX_SYSTEM` | `IMGCTX_TOOLS` | ON images |
| --- | --- | --- | --- |
| baseline | 0 | 1 | tools + tool output + history (part of the warm prefix) |
| `--tools0` | 0 | 0 | only the read-once document |

Reproduce: `.venv/bin/python -m bench.hotpot_claude_experiment --n 5 --model sonnet --tools0`

## Result: the cost sign flips with the config

| metric (n=5, matched pairs) | baseline `SYSTEM=0` | `--tools0` `SYSTEM=0 TOOLS=0` |
| --- | ---: | ---: |
| `input_tokens` (fresh, 1x) | +0.0% | +0.0% |
| `cache_creation_input_tokens` (**write, 2x**) | **+80.2%** | **-34.6%** |
| `cache_read_input_tokens` (read, 0.1x) | -57.9% | +9.9% |
| `output_tokens` | +14.8% | +5.7% |
| input-side total | -35.1% | **-0.2%** |
| **real cost (`total_cost_usd`)** | **+44.0%** | **-25.4%** |

Absolute per-class token counts (OFF / ON):

| class | baseline OFF | baseline ON | tools0 OFF | tools0 ON |
| --- | ---: | ---: | ---: | ---: |
| cache write | 86,078 | 155,087 | 128,672 | 84,148 |
| cache read | 478,520 | 201,585 | 434,855 | 477,985 |
| real cost | `$0.7550` | `$1.0876` | `$0.9985` | `$0.7450` |

**Reading:** the cost follows the cache-**write** class exactly, in both directions. Imaging the warm tool prefix forces new writes (+80.2%) and the bill rises (+44.0%). Not imaging it leaves those writes alone (-34.6%) and the bill falls (-25.4%). **The lever was config (which region we imaged), not the task itself.** This is the mechanism predicted in the deep-dive, Section 9.

## The honesty guard: do not cite the -25% as a compression win

The same rerun shows HotpotQA is a **poor yardstick for imgctx on Claude Code**, so the -25% must be read carefully:

- **Almost nothing here is compressible.** The HotpotQA document is ~1,300 tokens; Claude Code's own fixed system prompt + tool schemas are ~118,000 tokens per call. Compressible content is ~1% of the request. Imaging it removed ~700 of ~118,000 tokens. That is why input-side tokens moved only **-0.2%**.
- **So the -25% dollars did not come from compression.** With tokens essentially flat, the dollar drop is cache bookkeeping between the paired ON and OFF runs: once ON keeps the prefix as text, its bytes match OFF's, so ON reuses cache OFF just wrote rather than writing its own.
- **Proof it is bookkeeping, not signal:** the OFF arm's own cache-write moved 86,078 to 128,672 tokens between the baseline and tools0 sessions, for the **same** OFF config and questions, purely from different account-level cache warmth (1-hour TTL).

## Conclusions

1. **The `TOOLS=0` config removes the loss.** Imaging the warm, reusable prefix is what raised the Anthropic bill; leaving it as text and imaging only unique content does not. This is a targeting decision, available today as env flags.
2. **HotpotQA-through-Claude-Code cannot demonstrate token compression**, because ~99% of each call is Claude Code's fixed overhead, not compressible content. Its dollar figures (either sign) are dominated by cache accounting.
3. **The genuine "both tokens and dollars fall" evidence is the long-document family** (narrativeqa, gov_report), where the unique content is large relative to overhead: measured -13% to -18% real cost on the same model. See `bench/LONGDOC_REPORT.md`.
4. **The frame:** imgctx reduces input tokens on every provider; the dollar outcome is provider-specific, and the Anthropic re-send loss is one provider's price list, handled by targeting. See `docs/input-tokens-vs-cost.md` and Section 13 of `docs/understanding-tokens-cache-cost.md`.
