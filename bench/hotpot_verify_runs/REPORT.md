# HotpotQA post-refactor verification — all 4 CLIs

One HotpotQA question (n=1), A/B **off vs on**, through the refactored imgctx proxy.
Goal: confirm every CLI relay still works end-to-end after the per-CLI module split,
that image compression is actually built and sent, and that token/cost/cache is
recorded with **full raw request+response captured on disk** (no rerun needed).

## Result

| CLI | input off | input on | saved | cmp calls | images | F1 off/on | cost off→on |
|---|---|---|---|---|---|---|---|
| claude sonnet | 119,504 | 77,954 | −41,550 (35%) | — | — | 1.0/1.0 | $0.3994→$0.2686 (**−33%**) |
| codex gpt-5.4-mini | 38,315 | 24,832 | −13,483 (35%) | 3 | 6 | 1.0/1.0 | n/a (ChatGPT subscription) |
| opencode mimo-2.5 | 46,879 | 41,231 | −5,648 (12%) | 2 | 10 | 1.0/1.0 | n/a (free) |
| opencode-oauth gpt-5.4-mini | 37,304 | 35,217 | −2,087 (6%) | 2 | 8 | 1.0/1.0 | n/a (ChatGPT subscription) |

All four answered correctly in both arms; every ON arm sent real page images and cut
input tokens. Claude reports its own `total_cost_usd` → real −33% dollar cut. Codex &
opencode-oauth run on a ChatGPT subscription (no per-call price); mimo is free — for
those, token reduction is the measure.

## What each proves about the refactor

- **claude** — Anthropic `/v1/messages` relay: moved `read_oauth_token` (bearer injected,
  200 not 401) + moved `parse_usage` (cache-aware usage recorded).
- **codex** — native Responses relay in `codex.py`: `transform_responses_native` imaged the
  ~13k system prompt (3 blocks / 6 pages) in place, native SSE streamed back, correct answer.
- **opencode-oauth** — `opencode.py`: chat→responses conversion + SSE convert-back + OAuth
  inject, imaging through the relay.
- **opencode mimo** — generic chat path (unchanged), tool-doc/history imaging.

## Raw capture (per arm, `capture/` or `capture_on|off/`)

- `req_<ts>_in.json` — raw original request (full)
- `req_<ts>_out.json` — exact bytes sent upstream, **imaged** (base64 PNG data-URLs for
  the OpenAI/codex paths; Anthropic `image`/`source.base64` blocks for claude). e.g. claude
  ON req_out = 6.0 MB with 13 image blocks; codex/opencode ON req_out ≈ 2 MB with PNGs.
- `resp_<ts>.json` — **full** streamed upstream response (no head/tail truncation)
- `req_*_in_headers.json` / `resp_*_headers.json` — headers (request secrets redacted)
- `events.jsonl` — per-call usage (native shape, incl. cache split under
  `input_tokens_details` / Anthropic top-level)

## Notes / honesty

- **codex doc-read regime doesn't apply here.** codex's sandboxed shell (`bwrap`) can't
  create a namespace in this environment, so it can't cat the doc into a large tool result,
  and the HotpotQA doc (4,685 chars) is under the 6,000-char tool-result threshold anyway.
  So the codex ON arm images its **system prompt** instead (the reliably-large region on
  the codex path). The relay + imaging + capture are all exercised; only the imaged *region*
  differs from the doc-imaging arms.
- n=1 is a wiring/□correctness check, **not** a statistically meaningful compression benchmark.
