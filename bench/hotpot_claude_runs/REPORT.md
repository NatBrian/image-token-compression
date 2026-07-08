# HotpotQA: imgctx A/B on Claude Code, real cost

Claude Code CLI (`claude -p`) answering HotpotQA (distractor) multihop questions, each run twice through an identical proxy: compression OFF (passthrough) and ON (imgctx). Each question's 10 context paragraphs are written to a `documents.md`; the agent reads it and returns one `FINAL ANSWER:` line.

Model(s) seen in streams: `claude-sonnet-5`.

**All dollars are Claude Code's own `total_cost_usd`** (read from each run's stream). Tokens are Claude's real per-field usage. No price formula is used; the only math is summation and percent-change over these real values.

## Headline, matched n=5 (real cost)

| metric | OFF | ON | change |
| --- | ---: | ---: | ---: |
| input tokens (real) | 592,748 | 384,822 | **-35.1%** |
| cost, real total_cost_usd | $0.7550 | $1.0876 | **+44.0%** |
| exact match | 3/5 | 2/5 | |
| contains gold | 4/5 | 4/5 | |

## Per-question (real)

| qid | in OFF | in ON | Δ tok | $ OFF | $ ON | Δ $ | EM O/N | turns O/N |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :--: | :--: |
| q00 | 118,454 | 77,159 | -34.9% | $0.1502 | $0.2181 | +45% | 1/1 | 2/2 |
| q01 | 118,441 | 77,170 | -34.8% | $0.1509 | $0.2189 | +45% | 0/0 | 2/2 |
| q02 | 118,976 | 76,181 | -36.0% | $0.1533 | $0.2133 | +39% | 1/1 | 2/2 |
| q03 | 118,240 | 76,967 | -34.9% | $0.1494 | $0.2176 | +46% | 1/0 | 2/2 |
| q04 | 118,637 | 77,345 | -34.8% | $0.1512 | $0.2196 | +45% | 0/0 | 2/2 |
