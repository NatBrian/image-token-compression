# Combined A/B: imgctx ON vs OFF on Claude Code

One parallel run of two benchmarks through the real Claude Code CLI, each instance/question resolved twice (compression OFF passthrough vs ON). **All dollars are Claude Code's own `total_cost_usd`; all tokens are Claude's real per-field usage.** No price formula anywhere, the only math is summation and percent-change over these real values.

- SWE-bench Lite (long agentic), model `claude-sonnet-5`, matched n=5
- HotpotQA (short read-a-doc QA), model `claude-sonnet-5`, matched n=5

## Headline, real numbers

| benchmark | input tokens OFF→ON | Δ tokens | real cost OFF→ON | Δ cost |
| --- | --- | ---: | --- | ---: |
| SWE-bench (claude-sonnet-5) | 1,627,877 → 1,225,093 | **-24.7%** | $1.1988 → $1.5167 | **+26.5%** |
| HotpotQA (claude-sonnet-5) | 592,748 → 384,822 | **-35.1%** | $0.7550 → $1.0876 | **+44.0%** |

## Verdict

- **Tokens fall on both** (SWE-bench -24.7%, HotpotQA -35.1%), imaging + history-collapse genuinely shrink the request.
- **Real dollars rise on both** (SWE-bench +26.5%, HotpotQA +44.0%). Fewer tokens ≠ fewer dollars: on Anthropic, OFF's repeated context is already cheap cache-reads, and imaging converts those into cache-WRITES billed at the 1-hour TTL (~2x input).
- **Short-trajectory QA is hit harder than long agentic work**: HotpotQA (2 turns, no later turns to amortize the write) loses more than SWE-bench (long loops let the frozen prefix cache-read across many turns).
- **Net**: on Sonnet, imgctx compression is a token win but a real-cost LOSS on both task shapes. Imaging pays only on cheap-vision models like `claude-fable-5` or no-cache providers. On cache-cheap Anthropic models, leave it OFF.
- **Correctness**: both runs completed every instance with 0 tool errors / 0 HTTP 400s; compression never broke tool use or answers.
