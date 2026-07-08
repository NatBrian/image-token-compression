# imgctx

**A transparent proxy that renders bulky text context into images before it reaches a vision-capable LLM, cutting input tokens without changing your coding-agent CLI.**

`imgctx` sits between an OpenAI-compatible CLI (for example [OpenCode][OpenCode]) and the model provider. It intercepts each request, renders the large text regions (system prompt, tool docs, tool output, old history) to compact PNG pages, and forwards them as image blocks. Tool definitions, tool-call linkage, and multi-turn structure are preserved, so the agent behaves exactly as before while paying for far fewer input tokens.

```
your CLI  ->  imgctx proxy  ->  model provider
              (renders bulk text to images,
               streams the reply back untouched)
```

## Why it matters

An image's token cost is fixed by its pixel area, not by how many characters it contains. Dense content (code, JSON, logs, tool output) packs many characters into few image tokens. Agentic coding sessions re-send a large, mostly-static context on every step (system prompt, tool schemas, prior file reads), so that context dominates the bill. Rendering it to images cuts the dominant cost with no change to the CLI and no model fine-tuning.

## Results

Measured end-to-end on **HotpotQA** multihop questions driven through the **real OpenCode CLI** (`opencode run`, model `mimo-v2.5-free`). Same questions run twice, once with `imgctx` and once in pure passthrough, logged by the same proxy.

![Input tokens per question, with vs without imgctx](docs/assets/tokens_per_question.png)

| metric                             | without imgctx | with imgctx |           change |
| ---------------------------------- | -------------: | ----------: | ---------------: |
| median input tokens / question     |         46,454 |      28,464 | **-38.7%** |
| matched-trajectory subset (9/10 q) |        418,307 |     255,498 | **-38.9%** |
| exact match                        |           7/10 |        7/10 |                0 |
| answer-contains-gold               |           7/10 |        8/10 |               +1 |

Accuracy holds (no exact-match loss) on a hard multihop set with a small, free 9B-class reader.

### Isolated compression (single request)

To isolate the compression from agent nondeterminism, the same payload is sent once as text and once imaged (`python -m bench.ab`), and the provider-billed `prompt_tokens` compared. A needle is embedded in each payload to confirm the model still reads it.

| payload      | text tokens | imaged tokens |           change | needle recalled |
| ------------ | ----------: | ------------: | ---------------: | :-------------: |
| dense code   |      18,138 |         5,288 | **-70.8%** |       yes       |
| 51 KB JSON   |      24,565 |         5,477 | **-77.7%** |       yes       |
| sparse prose |       3,615 |         2,159 |           -40.3% |       yes       |

On a real captured OpenCode request (system prompt + 34 tool schemas + a file-read result), the residual text that stays as tokens drops from **123,656 to 15,097 characters (-87.8%)**, with all 34 tools preserved and tool calling intact.

### Bounding agent loops

Agentic runs sometimes loop (the model re-reads and retries), and each looped step re-sends the accumulating imaged context, which could cost more end-to-end. `imgctx` freezes old, settled turns into byte-identical images the provider caches (it reports `cached_tokens` on them), so looped sessions stay bounded. In the run above, the end-to-end input-token total across every call was **-32.6%** versus passthrough, and the one question that did loop stayed cheap because its old turns were served from cache. Agent looping is nondeterministic and n is small, so treat the end-to-end figure as indicative; the mechanism (byte-stable, cacheable history images) is verified separately.

### Dollar cost

`mimo-v2.5-free` is free, so the saving is measured in tokens. Applied to a paid model's input-token price, the median cut of **17,990 input tokens per question** is worth:

![Dollar saved per 1,000 questions across input prices](docs/assets/cost_savings.png)

| input price ($ / 1M tokens) | saved per 1,000 questions |
| --------------------------- | ------------------------: |
| $0.50                       | $9                        |
| $1.25                       | $22                       |
| $3.00                       | $54                       |
| $5.00                       | $90                       |
| $10.00                      | $180                      |

This counts input tokens only. Some providers bill image inputs on a separate schedule; on `mimo` the image cost is folded into `prompt_tokens`, so the measured token figure already includes it. Reproduce every number with `python -m bench.hotpot_experiment --n 10 && python -m bench.make_report && python docs/make_charts.py`.

## Demo

```console
$ imgctx serve
imgctx v0.1.0 proxy on http://127.0.0.1:8787
  -> upstream https://opencode.ai/zen/v1

# point OpenCode's provider at the proxy (examples/opencode.json), then:
$ opencode run --model opencode/mimo-v2.5-free \
    "read documents.md and answer: were Scott Derrickson and Ed Wood the same nationality?"
> Read documents.md
yes

# same question, measured by the proxy:
#   without imgctx : 46,283 input tokens
#   with imgctx    : 28,552 input tokens   (-38%, same answer)
```

## Architecture

```mermaid
flowchart LR
    CLI["Coding-agent CLI<br/>(OpenCode, ...)"] -->|POST /v1/chat/completions| P
    subgraph P["imgctx proxy"]
        R{"eligible request?<br/>vision model, POST"}
        R -->|no| PT["pass through unchanged"]
        R -->|yes| T["transform: pick regions,<br/>gate, render to PNG,<br/>splice image blocks"]
    end
    T -->|rewritten body| U["model provider<br/>(OpenAI-compatible)"]
    PT --> U
    U -->|streamed reply| CLI
```

The proxy only rewrites the request body. The response is streamed back byte-for-byte. Any parse error, unknown shape, or unsupported model falls through as a plain passthrough.

## How it works

Each request is split into regions, and each region is compressed only when it pays off:

1. **System prompt** and **tool documentation** are rendered to images. Tool schemas in `tools[]` are kept as JSON but stripped to their structure (names, parameter types, `required`, `enum`), so the provider can still validate tool calls while the verbose descriptions move into pixels.
2. **Tool outputs** (file reads, command output) and **older user messages** are imaged in place; the live (most recent) user turn always stays as text for full fidelity.
3. **Old conversation history** is collapsed: the settled, closed prefix (never cutting between a tool call and its result) is frozen into byte-identical image chunks that the provider caches, while the recent tail stays as text.

Two guards keep it safe and profitable:

- **Profitability gate.** Image-token cost is proportional to pixel area. A block is imaged only when its estimated image cost is below its text-token cost, and only above a per-region size floor, so sparse or tiny blocks stay text.
- **Verbatim safety.** Vision models read rendered text as embeddings, not OCR, so exact strings (hashes, UUIDs, secrets) can fail silently. `imgctx` keeps identifier-dense and secret-bearing blocks as text, and for any block it does image, it extracts the exact tokens (paths, hashes, versions, numbers, flags) and carries them alongside the image as plain text.

Rendering is deterministic: the same text always produces the same PNG bytes, which is what lets frozen history images hit the provider's automatic prompt cache turn after turn.

## Quick start

Requirements: Python 3.10+, `poppler-utils` (`pdftoppm`) on `PATH`, and an OpenAI-compatible upstream with a multimodal model.

```bash
git clone https://github.com/NatBrian/image-token-compression
cd image-token-compression
pip install -e .
imgctx serve            # proxy on http://127.0.0.1:8787
```

### Use it in a coding-agent CLI

Point the CLI's provider base URL at the proxy. For OpenCode (`~/.config/opencode/opencode.json`, see `examples/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "opencode": { "options": { "baseURL": "http://127.0.0.1:8787/v1" } }
  }
}
```

Then use OpenCode as usual:

```bash
opencode run --model opencode/mimo-v2.5-free "read src/app.py and explain what it does"
imgctx stats            # summarize tokens saved from ~/.imgctx/events.jsonl
```

Any OpenAI-compatible CLI works the same way: set its base URL to `http://127.0.0.1:8787/v1` and set `IMGCTX_UPSTREAM_BASE` to the real endpoint.

### Configuration

All settings are environment variables:

| variable                                                                                                   | default                              | meaning                                             |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------- |
| `IMGCTX_PORT`                                                                                            | `8787`                             | proxy port                                          |
| `IMGCTX_UPSTREAM_BASE`                                                                                   | `https://opencode.ai/zen/v1`       | real upstream (OpenAI-compatible)                   |
| `IMGCTX_MODELS`                                                                                          | `mimo,gemini,gpt-4,gpt-5,qwen,glm` | vision allowlist (substring match);`off` disables |
| `IMGCTX_TOOLS` / `IMGCTX_SYSTEM` / `IMGCTX_TOOL_RESULTS` / `IMGCTX_USER_TEXT` / `IMGCTX_HISTORY` | on                                   | per-region toggles                                  |
| `IMGCTX_MIN_TOOL_RESULT_CHARS` / `IMGCTX_MIN_USER_TEXT_CHARS`                                          | `6000`                             | per-region size floor                               |
| `IMGCTX_MIN_SYSTEM_CHARS` / `IMGCTX_MIN_TOTAL_CHARS`                                                   | `2000`                             | slab and whole-request floors                       |
| `IMGCTX_DPI`                                                                                             | `96`                               | render DPI (lower = denser, higher = more legible)  |
| `IMGCTX_MAX_PIXELS`                                                                                      | `1000000`                          | per-image pixel cap (avoid provider downscaling)    |
| `IMGCTX_KEEP_SHARP` / `IMGCTX_FACTSHEET`                                                               | on                                   | verbatim-safety features                            |
| `IMGCTX_ENABLED`                                                                                         | on                                   | master switch (`0` = pure passthrough)            |

## Known limitations

- **Lossy for exact strings inside images.** Byte-exact recall (hashes, UUIDs, secrets) is unreliable and fails silently. Mitigated (kept as text plus a factsheet), not eliminated. Byte-critical content should stay text.
- **Reader-model dependent.** Comprehension varies by model; keep the allowlist to models you have validated. Weaker readers can lose some accuracy on hard tasks.
- **Latency.** Rendering adds time to large requests before they leave, and vision encoding adds server-side time.
- **Wins on dense content.** Sparse prose has little to gain; the gate skips content where imaging would cost more than it saves.
- **Agent-loop variance.** History collapse bounds looped-session cost, but agent looping is nondeterministic and not fully eliminated.

## Inspired by

- *Text or Pixels? It Takes Half: On the Token Efficiency of Visual Text Inputs in Multimodal LLMs* ([arXiv:2510.18279](https://arxiv.org/abs/2510.18279))
- *LensVLM: Selective Context Expansion for Compressed Visual Representation of Text* ([arXiv:2605.07019](https://arxiv.org/abs/2605.07019))

`imgctx` is an independent implementation of the render-text-as-image idea, built as a transparent proxy for coding-agent CLIs.

## License

MIT, see [LICENSE](LICENSE).

[OpenCode]: https://opencode.ai
