# imgctx, HotpotQA End-to-End Experiment

Multihop QA (HotpotQA distractor, validation split) driven through the **real OpenCode CLI** (`opencode run`, model `mimo-v2.5-free`). Each question's 10 context paragraphs are written to `documents.md`; OpenCode reads the file (tool call) and answers. Every LLM call is routed through the imgctx proxy and its token usage logged. **OFF** = proxy in pure-passthrough mode; **ON** = imgctx compression active. Same questions, same instrument.

## Headline

_Token deltas are ON relative to OFF: **negative = fewer tokens (savings)**._

- **Per-request compression (median prompt tokens/question): 46,454 → 28,464 (-38.7%)**
- **Matched-trajectory subset (9/10 questions where OFF and ON used the same # of calls): 418,307 → 255,498 (-38.9%)**, the cleanest isolation of the compression effect
- Raw total across ALL calls: 465,300 → 313,441 (-32.6%) , dominated by 1 agent-loop outlier(s), see below
- Questions: 10 | LLM calls OFF 30 / ON 32
- Exact match: OFF 7/10 · ON 7/10  | answer-contains-gold: OFF 7/10 · ON 8/10
- Mean F1: OFF 0.757 · ON 0.879
- **Accuracy vs savings:** no accuracy loss (small-n, hard multihop; see per-question table)
- Images rendered (ON): 259 across 32 compressed calls
- Regions imaged (ON): {'system': 32, 'tools': 22, 'tool_result': 7}
- Wall time: OFF 101s · ON 544s (imaging adds render + vision-encode latency)

## Token usage per question (all OpenCode calls summed)

| qid | doc chars | OFF calls | OFF prompt tok | ON calls | ON prompt tok | Δ prompt tok | ON images |
|---|---:|---:|---:|---:|---:|---:|---:|
| q00 | 4,677 | 3 | 46,283 | 3 | 28,552 | -38.3% | 23 |
| q01 | 5,032 | 3 | 46,435 | 3 | 28,828 | -37.9% | 23 |
| q02 | 6,665 | 3 | 46,666 | 3 | 28,105 | -39.8% | 24 |
| q03 | 3,573 | 3 | 46,119 | 3 | 28,376 | -38.5% | 23 |
| q04 | 5,747 | 3 | 46,462 | 3 | 28,002 | -39.7% | 24 |
| q05 | 5,048 | 3 | 46,508 | 3 | 28,765 | -38.2% | 23 |
| q06 | 7,884 | 3 | 46,993 | 5 | 57,943 | +23.3% | 48 |
| q07 | 14,097 | 3 | 46,963 | 3 | 28,183 | -40.0% | 24 |
| q08 | 5,658 | 3 | 46,424 | 3 | 28,638 | -38.3% | 23 |
| q09 | 5,967 | 3 | 46,447 | 3 | 28,049 | -39.6% | 24 |
| **total** | | | **465,300** | | **313,441** | **-32.6%** | |

## Correctness per question (ON vs OFF)

| qid | question | gold | OFF pred | OFF em/ct | ON pred | ON em/ct |
|---|---|---|---|:--:|---|:--:|
| q00 | Were Scott Derrickson and Ed Wood of the same nationality? | yes | yes | 1/1 | yes | 1/1 |
| q01 | What government position was held by the woman who portrayed… | Chief of Protocol | United States ambassador | 0/0 | United States ambassador to Ghan | 0/1 |
| q02 | What science fantasy young adult series, told in first perso… | Animorphs | Animorphs | 1/1 | Animorphs | 1/1 |
| q03 | Are the Laleli Mosque and Esma Sultan Mansion located in the… | no | No | 1/1 | No | 1/1 |
| q04 | The director of the romantic comedy "Big Stone Gap" is based… | Greenwich Village, New York City | Greenwich Village | 0/0 | New York City | 0/0 |
| q05 | 2014 S/S is the debut album of a South Korean boy group that… | YG Entertainment | YG Entertainment | 1/1 | YG Entertainment | 1/1 |
| q06 | Who was known by his stage name Aladin and helped organizati… | Eenasul Fateh | Eenasul Fateh | 1/1 | Eenasul Fateh | 1/1 |
| q07 | The arena where the Lewiston Maineiacs played their home gam… | 3,677 seated | 4,000 | 0/0 | 3,677 | 0/0 |
| q08 | Who is older, Annie Morton or Terry Richardson? | Terry Richardson | Terry Richardson | 1/1 | Terry Richardson | 1/1 |
| q09 | Are Local H and For Against both from the United States? | yes | Yes | 1/1 | Yes | 1/1 |

## Agent-loop outliers (raw-total confound)

Questions where the ON agent ran **more tool-loop iterations** than OFF. Each extra turn re-sends the *accumulating* imaged context, so cost compounds. This is trajectory nondeterminism (the model chose to loop), not a per-request cost of compression, but it is a real risk the design must bound (image budget across turns / history collapse).

| qid | OFF calls | ON calls | OFF tok | ON tok |
|---|---:|---:|---:|---:|
| q06 | 3 | 5 | 46,993 | 57,943 |

## Notes

- **Trajectory variance:** OpenCode is an autonomous agent; the number of LLM calls per question can differ between OFF and ON runs (tool-loop nondeterminism). Token totals are summed over *all* calls in each run, so a differing call count is part of the honest comparison; the per-call and per-request savings (see the main README A/B) isolate the compression effect from trajectory noise.
- **Correctness parity** is the key safety signal: imaging the context should not reduce answer accuracy. Compare the EM/contains columns ON vs OFF.
- **Instrument:** identical proxy for both conditions; OFF forwards bytes unchanged (`IMGCTX_ENABLED=0`) but still logs upstream-billed usage.
- Raw artifacts: `bench/hotpot_runs/<cond>/<qid>/` holds `documents.md`, `events.jsonl` (per-call usage + transform stats), and `stdout.txt` (trajectory).
