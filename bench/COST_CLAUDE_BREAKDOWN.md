# The one lever, at a glance

| benchmark | cache-WRITE tokens Δ | cache-WRITE $ Δ | total cost Δ |
| --- | ---: | ---: | ---: |
| SWE-bench (re-read loop) | +87.6% | $+0.4836 | +26.5% |
| HotpotQA (re-read, short) | +80.2% | $+0.4141 | +44.0% |
| narrativeqa (read once) | -27.2% | $-0.3150 | -17.6% |
| gov_report (read once) | -26.4% | $-0.1931 | -14.8% |

Cache-write and total cost share a sign in every row: imaging that shrinks the write class lowers the bill; imaging that inflates it raises the bill.


# Cost decomposition by token class (simulation, reconciled to real cost)

**This is a standalone analysis, not part of the benchmark harness.** The harness only ever records Claude Code's real `total_cost_usd`. Here we take those same runs' REAL per-field token counts and multiply by PUBLISHED claude-sonnet-5 rates to see *which class* the money sits in. The reconciliation line on each block shows the simulated total lands on Claude's real bill, which is what makes the per-class split trustworthy.

Rates (USD per 1M tokens, 1-hour cache TTL as Claude Code uses): fresh input **3.00**, cache-WRITE **6.00** (2x), cache-read **0.30** (0.1x), output **15.00**.

## SWE-bench (re-read loop)  (matched n=5)

| token class | rate $/M | tokens OFF | tokens ON | Δ tok | $ OFF | $ ON | Δ $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh input (1x) | 3.00 | 28,324 | 28,332 | +0.0% | `$0.0850` | `$0.0850` | $+0.0000 |
| cache WRITE (2x, 1h) | 6.00 | 91,980 | 172,572 | +87.6% | `$0.5519` | `$1.0354` | $+0.4836 |
| cache read (0.1x) | 0.30 | 1,507,573 | 1,024,189 | -32.1% | `$0.4523` | `$0.3073` | $-0.1450 |
| output | 15.00 | 7,314 | 5,937 | -18.8% | `$0.1097` | `$0.0891` | $-0.0207 |
| **input-side (imaged)** | | 1,627,877 | 1,225,093 | -24.7% | `$1.0891` | `$1.4277` | $+0.3386 |
| **TOTAL (simulated)** | | | | | `$1.1988` | `$1.5167` | $+0.3179 (+26.5%) |

- **Reconciliation vs Claude's real `total_cost_usd`:** OFF sim `$1.1988` vs real `$1.1988` (diff $+0.0000); ON sim `$1.5167` vs real `$1.5167` (diff $+0.0000). Near-zero diff = the per-class split below is the real bill, not a guess.

- **What moved the bill:** cache-WRITE +0.4836, cache-read -0.1450, output -0.0207, fresh +0.0000. Net +0.3179. The write class is 152% of the |net| move.

## HotpotQA (re-read, short)  (matched n=5)

| token class | rate $/M | tokens OFF | tokens ON | Δ tok | $ OFF | $ ON | Δ $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh input (1x) | 3.00 | 28,150 | 28,150 | +0.0% | `$0.0844` | `$0.0844` | $+0.0000 |
| cache WRITE (2x, 1h) | 6.00 | 86,078 | 155,087 | +80.2% | `$0.5165` | `$0.9305` | $+0.4141 |
| cache read (0.1x) | 0.30 | 478,520 | 201,585 | -57.9% | `$0.1436` | `$0.0605` | $-0.0831 |
| output | 15.00 | 703 | 807 | +14.8% | `$0.0105` | `$0.0121` | $+0.0016 |
| **input-side (imaged)** | | 592,748 | 384,822 | -35.1% | `$0.7445` | `$1.0754` | $+0.3310 |
| **TOTAL (simulated)** | | | | | `$0.7550` | `$1.0876` | $+0.3325 (+44.0%) |

- **Reconciliation vs Claude's real `total_cost_usd`:** OFF sim `$0.7550` vs real `$0.7550` (diff $+0.0000); ON sim `$1.0876` vs real `$1.0876` (diff $+0.0000). Near-zero diff = the per-class split below is the real bill, not a guess.

- **What moved the bill:** cache-WRITE +0.4141, cache-read -0.0831, output +0.0016, fresh +0.0000. Net +0.3325. The write class is 125% of the |net| move.

## narrativeqa (read once)  (matched n=6)

| token class | rate $/M | tokens OFF | tokens ON | Δ tok | $ OFF | $ ON | Δ $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh input (1x) | 3.00 | 34,112 | 33,963 | -0.4% | `$0.1023` | `$0.1019` | $-0.0004 |
| cache WRITE (2x, 1h) | 6.00 | 193,032 | 140,534 | -27.2% | `$1.1582` | `$0.8432` | $-0.3150 |
| cache read (0.1x) | 0.30 | 2,142,697 | 1,848,227 | -13.7% | `$0.6428` | `$0.5545` | $-0.0883 |
| output | 15.00 | 9,845 | 12,694 | +28.9% | `$0.1477` | `$0.1904` | $+0.0427 |
| **input-side (imaged)** | | 2,369,841 | 2,022,724 | -14.6% | `$1.9033` | `$1.4996` | $-0.4038 |
| **TOTAL (simulated)** | | | | | `$2.0510` | `$1.6900` | $-0.3610 (-17.6%) |

- **Reconciliation vs Claude's real `total_cost_usd`:** OFF sim `$2.0510` vs real `$2.0510` (diff $+0.0000); ON sim `$1.6900` vs real `$1.6900` (diff $+0.0000). Near-zero diff = the per-class split below is the real bill, not a guess.

- **What moved the bill:** cache-WRITE -0.3150, cache-read -0.0883, output +0.0427, fresh -0.0004. Net -0.3610. The write class is 87% of the |net| move.

## gov_report (read once)  (matched n=4)

| token class | rate $/M | tokens OFF | tokens ON | Δ tok | $ OFF | $ ON | Δ $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh input (1x) | 3.00 | 22,850 | 22,703 | -0.6% | `$0.0685` | `$0.0681` | $-0.0004 |
| cache WRITE (2x, 1h) | 6.00 | 122,059 | 89,880 | -26.4% | `$0.7324` | `$0.5393` | $-0.1931 |
| cache read (0.1x) | 0.30 | 1,893,249 | 1,657,109 | -12.5% | `$0.5680` | `$0.4971` | $-0.0708 |
| output | 15.00 | 8,748 | 11,607 | +32.7% | `$0.1312` | `$0.1741` | $+0.0429 |
| **input-side (imaged)** | | 2,038,158 | 1,769,692 | -13.2% | `$1.3689` | `$1.1045` | $-0.2644 |
| **TOTAL (simulated)** | | | | | `$1.5001` | `$1.2786` | $-0.2215 (-14.8%) |

- **Reconciliation vs Claude's real `total_cost_usd`:** OFF sim `$1.5001` vs real `$1.5001` (diff $-0.0000); ON sim `$1.2786` vs real `$1.2786` (diff $+0.0000). Near-zero diff = the per-class split below is the real bill, not a guess.

- **What moved the bill:** cache-WRITE -0.1931, cache-read -0.0708, output +0.0429, fresh -0.0004. Net -0.2215. The write class is 87% of the |net| move.
