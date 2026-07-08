# What imgctx saves, and what depends on your provider

**Short version: imgctx has one job, and it does it everywhere. It sends fewer input tokens. Whether fewer tokens also means fewer dollars is a separate question, and the answer is decided by your provider's pricing, not by imgctx.**

This page is the plain-language version. If you want the full mechanism with every benchmark number, read [Understanding Tokens, Prompt Caching, and Cost](understanding-tokens-cache-cost.md).

## The one thing to keep straight: tokens and dollars are two different things

Think of an LLM request as a package you mail.

- **Input tokens are the weight of the package.** imgctx makes the package lighter by rendering bulky text into compact images. This is what imgctx does, and it works on every provider.
- **Cost is what the courier charges to ship it.** Different couriers price the same package differently. Some give a discount for sending the *same* package again (that is prompt caching). imgctx cannot control the courier's price list. It only controls the weight.

So "imgctx cuts input tokens" and "imgctx cuts your bill" are **not the same claim**. The first is always true. The second depends on who is shipping and what you are shipping.

## What imgctx guarantees

**Fewer input tokens.** Measured, repeatedly, on real CLIs:

| where | input-token cut |
| --- | ---: |
| Isolated dense code payload | **-70.8%** |
| Isolated 51 KB JSON payload | **-77.7%** |
| OpenCode / HotpotQA end-to-end | **-33% to -47%** |
| LongBench long-document QA (Anthropic) | **-13% to -35%** |

That is the deliverable. Fewer tokens also means you can fit more into a fixed context window, which is its own win independent of price.

## What depends on your provider

Whether the lighter package costs less money depends on how your provider prices tokens, especially how it prices **prompt caching**.

| provider | how it prices a repeated context | does imaging risk raising cost? |
| --- | --- | --- |
| **Anthropic** (Claude) | Charges a **premium** to store a new chunk (a cache-write, ~1.25x to 2x), then a deep **discount** to reuse it (a cache-read, ~0.1x). | **Yes, on one workload shape.** If your big context is re-sent many times, Anthropic already serves it at 0.1x. Imaging makes it new bytes, which loses that discount and pays the write premium instead. |
| **OpenAI** | Cache-write is **free**; a cached read is ~0.5x. No storage premium. | **Much less.** There is no 2x write premium to trip over, so the lighter package mostly just costs less. |
| **OpenRouter** | Passes through to whichever model it routes to. | Inherits that model's rules (Anthropic route behaves like Anthropic, OpenAI route like OpenAI). |
| **No-cache providers** | Every repeated token is billed full rate every time. | **No.** Fewer tokens is a straight dollar cut. Measured **-33% to -47%** on the OpenCode/`mimo` path. |

The takeaway: **the one case where imaging can raise the bill is Anthropic-style caching on a re-send-heavy workload.** It is a property of that provider's price list, not a defect in imgctx. On a provider that does not charge a cache-write premium, the same token cut just lowers the bill.

## Why the Anthropic re-send case is special (in one paragraph)

Anthropic's prompt cache is keyed on **exact bytes**. Rendering text to an image always produces new bytes, so it always counts as storing something new (a cache-write, the priciest input class). If your big context was going to be **re-sent many times**, Anthropic was already serving it from cache at the cheap 0.1x read rate, and imaging throws that discount away to pay the 2x write instead. If your big context is **unique and read once**, there was never a cheap cached copy to lose, so imaging simply makes the one unavoidable write smaller, and the bill goes **down**. Same tool, same provider, opposite result, decided entirely by how many times the context repeats. On Anthropic Sonnet we measured read-once work at **-13% to -18% real dollars**, and re-send-heavy agentic loops at **+26% to +44%**.

## A caution about measuring cost on tiny-context tasks

One benchmark deserves a footnote so nobody draws the wrong conclusion from it.

On **HotpotQA driven through Claude Code**, the document you actually want to compress is small (~1,300 tokens), while Claude Code's own fixed system prompt and tool schemas are large (~118,000 tokens on every call). So the compressible content is only about **1% of the request**. Imaging it removes ~700 tokens out of ~118,000. That is too little to demonstrate token compression, and any dollar figure from that task is dominated by cache bookkeeping between the paired ON and OFF runs, not by imaging. **HotpotQA-through-Claude-Code is a poor yardstick for imgctx, in either direction.** The honest place to measure both token and cost impact is a task where the unique content is large relative to the fixed overhead, which is exactly the long-document benchmarks (narrativeqa, gov_report).

## How to use imgctx well

1. **Expect the token cut everywhere.** That is what imgctx is for, and it is provider-independent.
2. **Expect the dollar cut when the big context is unique and read once**: long-document QA, summarization, classification, one-pass extraction, a big log or transcript pasted once. True even on Anthropic.
3. **On Anthropic, do not image a context that repeats every turn** (a long agentic loop). Anthropic already makes that cheap with caching. Leave that region as text (`IMGCTX_TOOLS=0`, `IMGCTX_SYSTEM=0`) or turn imaging off there.
4. **On providers without a cache-write premium** (OpenAI, no-cache upstreams), the token cut lands on the bill directly, with far less to worry about.

**Bottom line:** imgctx reliably reduces input tokens. That reduction turns into money on most providers and on read-once work everywhere. The single exception, Anthropic caching on a re-send-heavy workload, is a quirk of that provider's pricing, and it is handled by aiming imgctx at the right regions, not by any change to what imgctx does.
