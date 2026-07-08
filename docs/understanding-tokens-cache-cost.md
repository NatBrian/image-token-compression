# Understanding Tokens, Prompt Caching, and Cost

### A plain-language guide, using real imgctx benchmark data

This document explains, from zero, what a "token" is, how a large language model (LLM) provider charges you for one, what "prompt caching" does to that price, and exactly why `imgctx` (which turns text into images to save tokens) can make your bill go **down** on some jobs and **up** on others.

Everything here is backed by real measurements from four benchmarks run through the real Claude Code CLI on `claude-sonnet-5`. No number is invented. Where we split the bill by category, the split reproduces Claude's own reported cost **to the cent** (shown later), so you can trust it.

If you only read one thing, read this:

> `imgctx` always makes the **number** of input tokens go down. Whether that makes your **dollars** go down depends on one category of token called the **cache write**. When imaging shrinks the cache-write, you save money. When imaging accidentally *creates* cache-writes, you lose money. The rest of this doc explains why.

---

## Table of contents

1. [What is a token?](#1-what-is-a-token)
2. [Input tokens vs output tokens](#2-input-tokens-vs-output-tokens)
3. [What imgctx actually does](#3-what-imgctx-actually-does)
4. [Prompt caching: the one idea that explains everything](#4-prompt-caching-the-one-idea-that-explains-everything)
5. [How a bill is actually computed](#5-how-a-bill-is-actually-computed)
6. [The four benchmarks, with real numbers](#6-the-four-benchmarks-with-real-numbers)
7. ["Why is the token saving only -14%?"](#7-why-is-the-token-saving-only-14)
8. [Are we saving input tokens or total tokens? Does token affect cache or cost?](#8-are-we-saving-input-tokens-or-total-tokens)
9. [The cache-write is the lever: splitting the bill by category](#9-the-cache-write-is-the-lever)
10. ["Is cache-write secretly counting read tokens?"](#10-is-cache-write-secretly-counting-read-tokens)
11. [Why must SWE-bench and HotpotQA "re-shelve the book"?](#11-why-must-swe-bench-and-hotpotqa-re-shelve-the-book)
12. [Is the comparison cheating? Could OFF be using ON's cache?](#12-is-the-comparison-cheating)
13. [The honesty caveat: config vs task shape](#13-the-honesty-caveat)
14. [The final rule: when imgctx saves both tokens and money](#14-the-final-rule)
15. [Appendix: rates and how to reproduce](#15-appendix)

---

## 1. What is a token?

An LLM does not read letters or words. It reads **tokens**. A token is a small chunk of text, roughly 3 to 4 characters, or about 0.75 words on average. For example, the sentence "The cat sat." might be 4 tokens: `The`, ` cat`, ` sat`, `.`

Two things matter:

- **You are billed per token**, not per word or per request.
- **Everything you send and everything the model replies with is measured in tokens.**

So if you send a 10,000-word document, that is roughly 13,000 tokens, and you pay for all of them.

---

## 2. Input tokens vs output tokens

Every request to the model has two sides:

| side | what it is | who writes it |
| --- | --- | --- |
| **input** (also called "prompt") | everything you SEND: your question, the system instructions, tool descriptions, documents, the conversation so far | you / your tool |
| **output** (also called "completion") | everything the model REPLIES with | the model |

**Output tokens are much more expensive than input tokens** (on `claude-sonnet-5`, output is $15 per million, base input is $3 per million, 5x more).

Key fact for this whole document:

> `imgctx` **only changes the input**. It compresses the text you send. It never touches the output. In fact, in our benchmarks the output sometimes got slightly **bigger** with `imgctx` on, because the model happened to reply more verbosely. That is normal LLM randomness and is not something `imgctx` controls.

This is why, when we measure `imgctx`, we focus on **input tokens**. But (spoiler) we cannot ignore the total bill, because the total bill is what you actually pay, and it can move the opposite way from the token count.

---

## 3. What imgctx actually does

An image's token cost is fixed by its **pixel size**, not by how much text it contains. A single image page can hold a whole screen of dense text but only "cost" as many tokens as its area.

So `imgctx` takes bulky text regions (system prompt, tool descriptions, old tool output, old conversation history) and **renders them into image pages**, then sends those images instead of the text. Same information, far fewer input tokens.

```
Without imgctx:   [ 20,000 tokens of text ]  ->  model
With imgctx:      [ an image worth ~3,000 tokens ]  ->  model
```

That is the entire trick. It reliably lowers the **number** of input tokens. The hard question, and the reason this document exists, is what that does to the **price**.

---

## 4. Prompt caching: the one idea that explains everything

Here is the concept that makes cost behave in surprising ways.

Providers like Anthropic keep a **prompt cache**. Think of it as a **library**:

- The **first** time the provider sees a chunk of text, it "shelves" it. Shelving costs a one-time fee. This is a **cache write** (Anthropic calls it `cache_creation`).
- **Every later** request that repeats that exact chunk is "borrowed" off the shelf at a steep discount. This is a **cache read** (`cache_read`).
- If a chunk is brand-new and not worth shelving, it is just read once and thrown away. This is **fresh input** (`input_tokens`).

So **every input token falls into exactly one of three buckets**, and each bucket has a wildly different price:

| bucket | library analogy | price on `claude-sonnet-5` | vs base |
| --- | --- | --- | --- |
| **cache read** | borrow a book already on the shelf | **$0.30 / million** | **0.1x** (cheapest) |
| **fresh input** | read a page once, throw it out | $3.00 / million | 1x |
| **cache write** | print and shelve a brand-new book | **$6.00 / million** | **2x** (most expensive) |

*(The cache-write is 2x because Claude Code shelves books with a 1-hour expiry, the "1-hour TTL". A shorter 5-minute expiry costs 1.25x instead. Claude Code uses the 1-hour one.)*

Read that price table again, because it is the whole story:

> The **most expensive** thing you can do is shelve a new book (cache write, $6/M). The **cheapest** thing is borrow a shelved book (cache read, $0.30/M). They differ by **20x**.

This is why "fewer tokens" and "fewer dollars" can disagree. If you remove 100 cheap borrowed tokens ($0.30/M) but add 50 expensive shelving tokens ($6/M), your token count dropped but your bill went up.

**When is caching a good deal?** When you shelve a book once and then borrow it many times. A long agentic coding session re-sends the same system prompt and tool list every single turn, so after the first turn the provider serves almost all of it as cheap borrows. That is the ideal case for the cache.

---

## 5. How a bill is actually computed

The formula is simple:

```
total cost  =  (fresh tokens   x  $3/M)
            +  (cache-write tokens  x  $6/M)
            +  (cache-read tokens   x  $0.30/M)
            +  (output tokens   x  $15/M)
```

Notice two levers you can pull on the input side:

1. **How many** tokens there are (imgctx lowers this).
2. **Which bucket** they land in (imgctx can accidentally move them into the pricey cache-write bucket).

Lever 2 is the one everyone forgets, and it is the one that decides whether imgctx saves you money.

---

## 6. The four benchmarks, with real numbers

We ran four tasks, each twice: once with `imgctx` OFF (plain passthrough) and once ON. Same model (`claude-sonnet-5`), same tool (real Claude Code CLI). The four tasks come in two families:

| family | benchmark | what the task is | how the big context is used |
| --- | --- | --- | --- |
| **re-read loop** | SWE-bench Lite | fix a bug in a real code repo (long agentic loop) | the same context is re-read every turn, many turns |
| **re-read loop** | HotpotQA | read some paragraphs, answer a short question | short, but still a re-read shape |
| **read once** | LongBench narrativeqa | one long unique document (a book/script), answer a question | read a single time |
| **read once** | LongBench gov_report | one long unique government report, summarize it | read a single time |

Here is the complete real per-bucket token data. **OFF -> ON** and the percent change. The last two rows are the input-side subtotal (what imgctx affects) and the real dollar cost Claude itself reported.

### SWE-bench (re-read loop), 5 matched runs

| bucket | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 28,324 | 28,332 | +0.0% |
| **cache WRITE (2x)** | **91,980** | **172,572** | **+87.6%** |
| cache read (0.1x) | 1,507,573 | 1,024,189 | -32.1% |
| output | 7,314 | 5,937 | -18.8% |
| input-side total | 1,627,877 | 1,225,093 | **-24.7%** |
| **real cost** | **$1.1988** | **$1.5167** | **+26.5%** |

### HotpotQA (re-read, short), 5 matched runs

| bucket | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 28,150 | 28,150 | +0.0% |
| **cache WRITE (2x)** | **86,078** | **155,087** | **+80.2%** |
| cache read (0.1x) | 478,520 | 201,585 | -57.9% |
| output | 703 | 807 | +14.8% |
| input-side total | 592,748 | 384,822 | **-35.1%** |
| **real cost** | **$0.7550** | **$1.0876** | **+44.0%** |

### narrativeqa (read once), 6 matched runs

| bucket | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 34,112 | 33,963 | -0.4% |
| **cache WRITE (2x)** | **193,032** | **140,534** | **-27.2%** |
| cache read (0.1x) | 2,142,697 | 1,848,227 | -13.7% |
| output | 9,845 | 12,694 | +28.9% |
| input-side total | 2,369,841 | 2,022,724 | **-14.6%** |
| **real cost** | **$2.0510** | **$1.6900** | **-17.6%** |

### gov_report (read once), 4 matched runs

| bucket | OFF | ON | change |
| --- | ---: | ---: | ---: |
| fresh input (1x) | 22,850 | 22,703 | -0.6% |
| **cache WRITE (2x)** | **122,059** | **89,880** | **-26.4%** |
| cache read (0.1x) | 1,893,249 | 1,657,109 | -12.5% |
| output | 8,748 | 11,607 | +32.7% |
| input-side total | 2,038,158 | 1,769,692 | **-13.2%** |
| **real cost** | **$1.5001** | **$1.2786** | **-14.8%** |

Stare at the **cache WRITE** row and the **real cost** row across all four tables:

| benchmark | cache-write change | real cost change |
| --- | ---: | ---: |
| SWE-bench | **+87.6%** | +26.5% |
| HotpotQA | **+80.2%** | +44.0% |
| narrativeqa | **-27.2%** | -17.6% |
| gov_report | **-26.4%** | -14.8% |

**They share a sign every single time.** When cache-write goes up, the bill goes up. When cache-write goes down, the bill goes down. Hold onto that; Section 9 proves it is not a coincidence.

---

## 7. "Why is the token saving only -14%?"

Look at narrativeqa: the input-side total fell only **-14.6%**, even though imaging clearly compressed the document. Why so small?

Because **~90% of all input tokens are cache-reads** (2,142,697 out of 2,369,841). Those are the giant, cheap, borrowed-off-the-shelf tokens. The document that imgctx actually shrank is a smaller slice. So when you average everything into one "input tokens" number, the huge cheap-read pool **dilutes** the percentage.

The blended -14% is real, but it **understates the interesting part**. The interesting part is that the **cache-write** bucket fell **-27.2%**, twice as much, and that is the bucket that controls the bill. The blended number hides the lever. That is exactly why we now always break the tokens out by bucket instead of reporting one number.

---

## 8. Are we saving input tokens or total tokens?

Three quick answers to three natural questions:

**"Are we saving input tokens, or the whole total token count?"**
Input tokens. imgctx renders bulky **input** text into images. It never compresses the model's **output**. Total = input + output, and since input dwarfs output here, the total drops too, but 100% of the credit belongs to input. (In two benchmarks the output even grew, because the model replied more verbosely with imgctx on; that is randomness, not imgctx.)

**"Does the token count affect the cache?"**
No, it is the other way around. The **cache decides the price of each token.** A token's bucket (fresh / write / read) is a property assigned by the provider, and that bucket sets the price. imgctx changes both how many tokens there are and, as a side effect, which bucket they land in.

**"Does the token affect the cost?"**
Yes, through the formula in Section 5: `cost = sum over tokens of (count x price-of-its-bucket)`. So tokens drive cost in two ways at once: how many there are, and which priced bucket they sit in. imgctx wins on cost only when it does not push tokens into the expensive cache-write bucket.

**"So are we proving the wrong thing by looking at cost? Should we only look at input tokens?"**
No. Input tokens are the clean measure of what imgctx **does**, so we lead with them. But if we reported *only* tokens, we would repeat the exact mistake that made this project look good before we measured carefully: tokens fell, yet the real bill rose +26% to +44%. Cost is what your wallet feels, so we keep it. The honest position is: **lead with input tokens (and specifically the cache-write bucket), and confirm with the real dollar cost.** Our analysis is not wrong; the numbers are real and reconcile to the cent. We simply learned to look at the **cache-write bucket** instead of the blended token count.

---

## 9. The cache-write is the lever

We can prove the cache-write bucket is the bill by splitting each benchmark's real cost into its four buckets, using the price table from Section 4. This is a **simulation**, so we check it against Claude's own reported `total_cost_usd`. On every run it matches **to the cent**, which means the split is not a guess, it is literally the real bill re-sorted by category.

Dollars moved, by bucket (OFF -> ON):

| benchmark | **cache-WRITE $** | cache-read $ | output $ | fresh $ | **net $** | net % | reconciles? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :--: |
| SWE-bench | **+$0.484** | -$0.145 | -$0.021 | $0.000 | **+$0.318** | +26.5% | exact |
| HotpotQA | **+$0.414** | -$0.083 | +$0.002 | $0.000 | **+$0.333** | +44.0% | exact |
| narrativeqa | **-$0.315** | -$0.088 | +$0.043 | $0.000 | **-$0.361** | -17.6% | exact |
| gov_report | **-$0.193** | -$0.071 | +$0.043 | $0.000 | **-$0.221** | -14.8% | exact |

Read the SWE-bench row in words:

- imaging **added +$0.484** of cache-writes (it shelved new books),
- the cheap-read saving only gave back **-$0.145** (it borrowed a bit less),
- so the net is still **+$0.318 more expensive**.

The read discount can never catch up, because reads are $0.30/M and writes are $6/M. **Every token you move from the read shelf to the write printer costs 20x more.**

Three facts this table nails down:

1. **Fresh input contributes $0.000 everywhere.** Claude Code caches almost everything, so there is essentially no "fresh 1x input" to cut. Fresh input is not the lever. (An earlier version of our README wrongly credited "fresh input"; this data disproves that to the cent.)
2. **The output wobble you might worry about is tiny in dollars:** +$0.043 on the read-once winners. It nibbles about 12% off the win but never flips it. So output randomness does not make cost untrustworthy.
3. **Cache-write dollars and total dollars share a sign in all four rows.** That one bucket *is* the story.

---

## 10. "Is cache-write secretly counting read tokens?"

No. This is a common and reasonable confusion, so let us kill it directly.

`cache_creation` (write) and `cache_read` (read) are **two separate counters with no overlap.** On any single API call, each input token is placed in exactly one of them. They are reported side by side. For example, one real SWE-bench call:

```
call 1 (OFF):   cache WRITE = 9,050      cache READ = 43,118
```

Those are two different piles of tokens on the same call: 9,050 tokens were shelved, 43,118 different tokens were borrowed. The write count does **not** include the read count. "Cache write" is pure write.

So the reason ON has a bigger write total than OFF is **not** that write is quietly absorbing reads. The real reason is in the next section.

---

## 11. Why must SWE-bench and HotpotQA "re-shelve the book"?

This is the deepest question, and the answer is a hard rule about how the cache works.

### The cache is keyed on exact bytes

The provider's cache matches on the **literal bytes** of what you send. To borrow a book off the shelf (a cache read), the incoming bytes must be **byte-for-byte identical** to something already shelved. Change one byte and it is a different book that has to be shelved again.

### Imaging changes the bytes, by definition

The warm, already-shelved content in Claude Code is the standard **system prompt + tool descriptions, as text.** It is warm because it is identical on every turn, every task, and every prior session on your account.

Now imgctx turns that text into an **image**. An image is completely different bytes from the text it was rendered from. So:

```
Already shelved:   [ system TEXT ][ tools TEXT ]   <- warm, borrowed cheaply
imgctx ON sends:   [ system IMAGE ][ tools IMAGE ] <- totally different bytes
                   -> matches nothing on the shelf
                   -> cache MISS
                   -> must PAY A WRITE to shelve the new image
```

You cannot both "turn it into an image" **and** "keep borrowing the text version." The warm book is keyed on bytes that no longer exist in your request. This is not a bug you can patch away; it is what "change the representation" means.

### Watch it happen, call by call

Here is one real SWE-bench instance, every API call, OFF vs ON:

**OFF** (sends the standard text, which is already on the shelf):
```
call    WRITE     READ
  1     9,050    43,118    <- already borrowing 43k on the very first call
  2     6,128    52,168
  3     1,317    58,296
  4       346    59,613
 sum   33,682   426,390    read/write ratio = 12.7  (shelve once, borrow many)
```

**ON** (imgctx swapped the text for images):
```
call    WRITE     READ
  1    23,143     8,378    <- cache MISS: must shelve 23k of new image, borrows only 8k
  2    23,143     8,378    <- still shelving, cache not warm yet
  3     6,770    31,521
  4       450    39,053
 sum   84,943   203,811    read/write ratio = 2.4   (shelve a lot, borrow less)
```

OFF is **already warm on call 1** (43k borrowed). ON is **cold on call 1** (must shelve 23k of brand-new image bytes). Over the whole loop, OFF shelves 34k and borrows 426k (great deal); ON shelves 85k and borrows only 204k (bad deal). imgctx spent expensive writes to destroy cheap reads.

### So why does this hurt SWE-bench/HotpotQA but help narrativeqa/gov_report?

Because of **what** each one imaged:

| benchmark | what imgctx imaged | was it already warm? | outcome |
| --- | --- | --- | --- |
| SWE-bench / HotpotQA | the **system + tool** prefix | **YES, the warmest, cheapest thing in the whole request** | imaging destroyed the biggest existing discount and paid to rebuild a private, colder cache -> **write UP, bill UP** |
| narrativeqa / gov_report | only the **unique document** | **NO, a unique book nobody had shelved** | both OFF and ON must shelve the document once anyway; imgctx just shelved a **thinner** version -> **write DOWN, bill DOWN** |

That is the crux. On SWE-bench and HotpotQA, imgctx imaged **exactly the bytes that were already cached most cheaply.** That is the worst possible target: you spend a $6/M write to destroy a $0.30/M read. On narrativeqa and gov_report, imgctx left the warm prefix alone and imaged only the unique document, which was going to cost a write no matter what, so making it smaller was a pure win.

**One sentence:** imaging always produces new bytes, and new bytes always cost a cache-write; that write is *waste* when it replaces something already warm on the shelf, and it is a *saving* when it is just a smaller version of a write you had to pay anyway.

---

## 12. Is the comparison cheating?

A fair worry: since ON and OFF run the same benchmark against the same account, could OFF be secretly borrowing from a cache that ON created (or vice versa), making the comparison meaningless?

**Answer: no, and we can prove it two ways.**

### Proof 1: the caches physically cannot share on the compressed regions

The cache matches on exact bytes. On every region imgctx actually compresses, ON sends **images** and OFF sends **text**. Different bytes, so they can never match the same shelf entry. ON cannot borrow OFF's text; OFF cannot borrow ON's images. The regions that drive the entire result are physically isolated.

### Proof 2: the run-order timeline

We ran them in this order and recorded each run's very first call:

| order | arm | instance | call-1 WRITE | call-1 READ | state |
| ---: | --- | --- | ---: | ---: | --- |
| **1** | **off** | requests-1963 | 9,234 | **43,118** | **WARM** |
| 2 | on | requests-1963 | 23,327 | 8,378 | cold |
| 3 | off | flask-4045 | 9,050 | 43,118 | WARM |
| 4 | on | flask-4045 | 23,143 | 8,378 | cold |
| 5 | off | pylint-5859 | 9,438 | 43,118 | WARM |
| 6 | on | pylint-5859 | 23,531 | 8,378 | cold |

Two things this proves:

- **Run #1 is OFF, before any ON has ever run, and it is already WARM** (borrows 43,118 on its first call). That warmth cannot come from ON, because ON did not exist yet. It comes from your **account's standing cache** of the standard Claude Code prefix, warmed by all your normal `claude` usage. So OFF is definitely not "using ON's cache."
- **Run #2 is ON on the exact same instance OFF just ran, and it is still COLD** (shelves 23k, borrows only 8k). If the arms shared a cache, ON would be warm here. It is not, because OFF shelved *text* and ON needs *images*. So ON gets nothing from OFF either.

The tell-tale detail: every OFF first-call read is **identically 43,118** and every ON first-call read is **identically 8,378**, across all instances. Those are stable, structural cache states, not random leakage between arms.

### Which way does any residual bias point?

Against ON, not for it. OFF sends the standard text prefix that your account keeps permanently warm, so OFF is measured in its **best case**. ON sends bespoke images that nobody else warms, so ON pays a cold-start write on **every** instance. If anything, the measured ON loss is an **over-estimate** of ON's steady-state cost. We are not flattering imgctx; we are penalizing it.

Both arms are measured in their **realistic** states (OFF warm because in real life that prefix is warm; ON cold because in real life those images are bespoke), so the comparison is fair. To make it airtight you could isolate the caches with a unique per-arm nonce or separate API keys; the physics above says the compressed-region numbers would not move.

---

## 13. The honesty caveat

The four benchmarks are **not a perfectly clean apples-to-apples** experiment, because the two families used slightly different `imgctx` settings:

| family | `IMGCTX_SYSTEM` | `IMGCTX_TOOLS` | so it imaged... |
| --- | --- | --- | --- |
| SWE-bench / HotpotQA | 0 (system left as text) | **1 (tools imaged)** | tools + tool output + history, so it **did** image part of the warm prefix |
| narrativeqa / gov_report | 0 | **0 (tools left as text)** | only the unique document |

So the result mixes **task shape** (re-read vs read-once) with **config** (did we image the warm prefix or not). The lesson is the same either way: *do not image content that is already cached cheaply; do image unique content.* But to isolate task shape alone, the clean follow-up is to re-run SWE-bench and HotpotQA with `IMGCTX_TOOLS=0` as well, so no benchmark images the warm prefix. Our per-call analysis predicts that would shrink or even reverse the loss on those two.

---

## 14. The final rule

Put everything together into one decision:

> **Image content that is UNIQUE and paid for as a write anyway. Never image content that is already warm in the cache.**

Restated as a question to ask about any job:

- **Is the big context read once (a unique document, a report to summarize, a file to classify)?**
  Then nobody had it cached, both arms pay to shelve it once, and imaging just shelves a thinner version. **You save both tokens and money.** (Measured: -13% to -18% real cost on Anthropic Sonnet.)

- **Is the big context a fixed prefix re-read every turn of a long agentic loop?**
  Then the provider already serves it as cheap borrows, and imaging it forces expensive re-shelving. **Tokens fall but the bill rises.** (Measured: +26% to +44%.) Leave imgctx off for that content, or use it only for the token-count / context-window benefit.

Why "fewer tokens" and "fewer dollars" can disagree, in one line: a cache-read costs $0.30/M and a cache-write costs $6/M, a **20x gap**, so moving even a few tokens from the read bucket to the write bucket can raise the bill while lowering the count.

And the reassuring part: `imgctx` never broke anything. Across all four benchmarks, every run completed with 0 tool errors and 0 HTTP failures, and answer quality stayed within noise of the baseline. The economics change with the task; the behavior does not.

---

## 15. Appendix

### Price table used (claude-sonnet-5, USD per 1 million tokens)

| bucket | field name in the API | rate | multiple of base input |
| --- | --- | ---: | ---: |
| fresh input | `input_tokens` | $3.00 | 1x |
| cache write (1-hour TTL) | `cache_creation_input_tokens` | $6.00 | 2x |
| cache read | `cache_read_input_tokens` | $0.30 | 0.1x |
| output | `output_tokens` | $15.00 | 5x |

These are published Anthropic rates. Multiplying the real token counts by these rates reproduces Claude Code's own reported `total_cost_usd` to the cent on every benchmark, which is what lets us trust the per-bucket split.

### How to reproduce

```bash
# read-once winners
.venv/bin/python -m bench.longdoc_experiment --n 6 --config narrativeqa --model sonnet
.venv/bin/python -m bench.longdoc_experiment --n 4 --config gov_report  --model sonnet
.venv/bin/python -m bench.longdoc_report

# re-read losers
.venv/bin/python -m bench.swebench_experiment --n 5 --model sonnet
.venv/bin/python -m bench.hotpot_claude_experiment --n 5 --model sonnet
.venv/bin/python -m bench.swebench_report
.venv/bin/python -m bench.hotpot_claude_report

# the per-bucket dollar decomposition (this document's Section 9)
.venv/bin/python -m bench.cost_breakdown        # writes bench/COST_BREAKDOWN.md

# the token-vs-cost chart
.venv/bin/python docs/make_anthropic_chart.py
```

### Glossary

| term | meaning |
| --- | --- |
| token | a ~3-4 character chunk of text; the unit you are billed in |
| input / prompt | everything you send to the model |
| output / completion | everything the model replies |
| prompt cache | the provider's "library" that stores repeated text so it is cheap to reuse |
| cache write (`cache_creation`) | shelving new text into the cache; the most expensive input bucket (2x) |
| cache read (`cache_read`) | borrowing already-shelved text; the cheapest input bucket (0.1x) |
| fresh input (`input_tokens`) | text sent that is neither shelved nor borrowed; base price (1x) |
| TTL | how long a shelved chunk stays before it expires (Claude Code uses 1 hour) |
| warm / cold cache | whether the content you send is already on the shelf (warm) or brand-new (cold) |
| `total_cost_usd` | the real bill Claude Code reports; our ground truth for dollars |
