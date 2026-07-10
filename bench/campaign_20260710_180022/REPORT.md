# Campaign ON/OFF comparison

### claude_longdoc/results_gov_report.json
agent=`claude` family=`anthropic` benchmark=`gov_report`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 1,141,314 | 626,593 | -45.1% |
|   fresh | 11,427 | 11,272 |  -1.4% |
|   cache-read | 1,064,045 | 583,662 | -45.1% |
|   cache-write | 65,842 | 31,659 | -51.9% |
| output | 5,650 | 4,983 | -11.8% |
| **cost (real_provider)** | `$0.8333` | `$0.4736` | -43.2% |
| F1 (avg) | 0.121 | 0.101 | — |
| items / ON images | 2 / — | 2 / 0 | — |

### claude_longdoc/results_narrativeqa.json
agent=`claude` family=`anthropic` benchmark=`narrativeqa`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 304,987 | 320,168 |  +5.0% |
|   fresh | 11,260 | 11,262 |  +0.0% |
|   cache-read | 193,320 | 252,379 | +30.5% |
|   cache-write | 100,407 | 56,527 | -43.7% |
| output | 681 | 3,016 | +342.9% |
| **cost (real_provider)** | `$0.7044` | `$0.4939` | -29.9% |
| F1 (avg) | 0.186 | 0.174 | — |
| items / ON images | 2 / — | 2 / 0 | — |

### claude_swebench/results.json
agent=`claude` family=`anthropic` benchmark=`swebench`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 538,661 | 542,308 |  +0.7% |
|   fresh | 11,268 | 11,268 |  +0.0% |
|   cache-read | 449,231 | 494,720 | +10.1% |
|   cache-write | 78,162 | 36,320 | -53.5% |
| output | 1,594 | 1,319 | -17.3% |
| **cost (real_provider)** | `$0.6615` | `$0.4199` | -36.5% |
| F1 (avg) | - | - | — |
| items / ON images | 2 / — | 2 / 0 | — |

### codex_hotpot/results.json
agent=`codex` family=`openai` benchmark=`hotpot`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 72,049 | 67,442 |  -6.4% |
|   fresh | 16,113 | 11,122 | -31.0% |
|   cache-read | 55,936 | 56,320 |  +0.7% |
|   cache-write | 0 | 0 |   n/a |
| output | 1,754 | 1,171 | -33.2% |
| **cost (simulated)** | `$0.0242` | `$0.0178` | -26.2% |
| F1 (avg) | 0.834 | 0.500 | — |
| items / ON images | 2 / — | 2 / 16 | — |

### codex_longdoc/results_gov_report.json
agent=`codex` family=`openai` benchmark=`gov_report`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 165,623 | 135,792 | -18.0% |
|   fresh | 16,375 | 26,992 | +64.8% |
|   cache-read | 149,248 | 108,800 | -27.1% |
|   cache-write | 0 | 0 |   n/a |
| output | 3,776 | 2,454 | -35.0% |
| **cost (simulated)** | `$0.0405` | `$0.0394` |  -2.5% |
| F1 (avg) | 0.015 | 0.011 | — |
| items / ON images | 2 / — | 2 / 32 | — |

### codex_longdoc/results_narrativeqa.json
agent=`codex` family=`openai` benchmark=`narrativeqa`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 107,028 | 107,009 |  -0.0% |
|   fresh | 30,868 | 23,937 | -22.5% |
|   cache-read | 76,160 | 83,072 |  +9.1% |
|   cache-write | 0 | 0 |   n/a |
| output | 3,209 | 2,695 | -16.0% |
| **cost (simulated)** | `$0.0433` | `$0.0363` | -16.1% |
| F1 (avg) | 0.571 | 0.624 | — |
| items / ON images | 2 / — | 2 / 24 | — |

### codex_swebench/results.json
agent=`codex` family=`openai` benchmark=`swebench`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 95,453 | 77,343 | -19.0% |
|   fresh | 17,245 | 11,423 | -33.8% |
|   cache-read | 78,208 | 65,920 | -15.7% |
|   cache-write | 0 | 0 |   n/a |
| output | 4,843 | 2,595 | -46.4% |
| **cost (simulated)** | `$0.0406` | `$0.0252` | -37.9% |
| F1 (avg) | - | - | — |
| items / ON images | 2 / — | 2 / 18 | — |

### mimo_hotpot/results.json
agent=`mimo` family=`mimo` benchmark=`hotpot`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 120,678 | 57,657 | -52.2% |
|   fresh | 10,022 | 6,457 | -35.6% |
|   cache-read | 110,656 | 51,200 | -53.7% |
|   cache-write | 0 | 0 |   n/a |
| output | 1,160 | 2,342 | +101.9% |
| **cost (simulated)** | `$0.0021` | `$0.0017` | -16.8% |
| F1 (avg) | 0.834 | 0.650 | — |
| items / ON images | 2 / — | 2 / 42 | — |

### mimo_longdoc/results_gov_report.json
agent=`mimo` family=`mimo` benchmark=`gov_report`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 1,780,375 | 527,462 | -70.4% |
|   fresh | 143,895 | 72,230 | -49.8% |
|   cache-read | 1,636,480 | 455,232 | -72.2% |
|   cache-write | 0 | 0 |   n/a |
| output | 17,542 | 11,188 | -36.2% |
| **cost (simulated)** | `$0.0300` | `$0.0146` | -51.2% |
| F1 (avg) | 0.136 | 0.135 | — |
| items / ON images | 2 / — | 2 / 399 | — |

### mimo_longdoc/results_narrativeqa.json
agent=`mimo` family=`mimo` benchmark=`narrativeqa`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 226,432 | 95,009 | -58.0% |
|   fresh | 62,976 | 16,801 | -73.3% |
|   cache-read | 163,456 | 78,208 | -52.2% |
|   cache-write | 0 | 0 |   n/a |
| output | 982 | 38,614 | +3832.2% |
| **cost (simulated)** | `$0.0096` | `$0.0134` | +39.8% |
| F1 (avg) | 0.102 | 0.059 | — |
| items / ON images | 2 / — | 2 / 80 | — |

### mimo_swebench/results.json
agent=`mimo` family=`mimo` benchmark=`swebench`
| metric | OFF | ON | Δ |
|---|---:|---:|---:|
| input (total) | 1,772,755 | 655,714 | -63.0% |
|   fresh | 68,115 | 137,506 | +101.9% |
|   cache-read | 1,704,640 | 518,208 | -69.6% |
|   cache-write | 0 | 0 |   n/a |
| output | 20,711 | 7,682 | -62.9% |
| **cost (simulated)** | `$0.0204` | `$0.0230` | +12.3% |
| F1 (avg) | - | - | — |
| items / ON images | 2 / — | 2 / 564 | — |
