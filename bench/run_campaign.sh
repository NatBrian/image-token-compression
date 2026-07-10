#!/usr/bin/env bash
# Safe full-campaign launcher (ON/OFF, all live cells).
#
# Concurrency model: THREE lanes -- mimo, codex, claude -- run at the same time
# (different endpoints: zen / chatgpt / anthropic, so no shared rate limit). But
# WITHIN a lane the cells run strictly ONE AT A TIME. This keeps each account/endpoint
# from contending with itself -- in particular the FREE mimo/zen route, which returned
# "No provider available" under parallel load during the dry-run.
#
# Safety guards:
#   * per-cell collision guard: never launch a cell whose results file already exists
#     and is non-empty (prevents the double-launch-into-one-dir corruption we hit).
#   * swebench repo cache is pre-warmed SERIALLY and instances.json is pre-seeded into
#     every swebench cell, so the three lanes never race on git clone or the HF fetch.
#   * fresh timestamped output folder -- never overwrites an old run.
#
# Per-benchmark N and timeouts are variables below; override via env, e.g.
#   N_SWE=3 N_HOTPOT=20 bash bench/run_campaign.sh
set -u
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python

# ---- knobs (override via env) ----
N_HOTPOT=${N_HOTPOT:-10}
N_SWE=${N_SWE:-5}
N_NQA=${N_NQA:-8}
N_GOV=${N_GOV:-8}
T_SHORT=${T_SHORT:-360}     # hotpot
T_LONG=${T_LONG:-600}       # longdoc (loops -> give headroom)
T_SWE=${T_SWE:-600}         # swebench agentic

TS=$(date +%Y%m%d_%H%M%S)
RUN="campaign_${TS}"                 # relative to bench/ (drivers do HERE/args.runs_dir)
ABS="bench/${RUN}"
LOG="${ABS}/logs"
mkdir -p "$LOG"
echo "CAMPAIGN=$RUN  N: hotpot=$N_HOTPOT swe=$N_SWE nqa=$N_NQA gov=$N_GOV" | tee "${ABS}/CAMPAIGN.txt"

# ---- pre-warm swebench: select instances ONCE, checkout serially, seed every lane ----
echo "[prewarm] selecting + checking out $N_SWE swebench instances (serial)..." | tee -a "${ABS}/CAMPAIGN.txt"
$PY - "$N_SWE" "$ABS" <<'PY'
import sys, json, pathlib
from bench import swebench_claude_experiment as S
n = int(sys.argv[1]); absdir = pathlib.Path(sys.argv[2])
insts = S.select_instances(n)
for inst in insts:
    S.ensure_base_checkout(inst)   # populates the shared cache serially (no race)
for cell in ("mimo_swebench", "codex_swebench", "claude_swebench"):
    d = absdir / cell; d.mkdir(parents=True, exist_ok=True)
    (d / "instances.json").write_text(json.dumps(insts, indent=2))
print("[prewarm] done:", [i["instance_id"] for i in insts])
PY
[ $? -ne 0 ] && { echo "PREWARM FAILED -- abort"; exit 1; }

# ---- helpers ----
# guard <results_path> : returns 0 (run) if the file is absent/empty, 1 (skip) otherwise.
guard () { if [ -s "$1" ]; then echo "  SKIP (results exist): $1"; return 1; else return 0; fi; }

# cell <name> <results_relpath> <cmd...> : collision-guarded, logged, sequential run.
cell () {
  local name="$1"; local res="${ABS}/$2"; shift 2
  echo ">> $name"
  guard "$res" || return 0
  "$@" > "${LOG}/${name}.log" 2>&1
  echo "   $name exit=$? -> $2"
}

# ---- LANE: mimo (opencode/mimo-v2.5-free via zen) -- STRICTLY SEQUENTIAL, port 8830 ----
mimo_lane () {
  cell mimo_hotpot   "mimo_hotpot/results.json" \
    $PY -m bench.hotpot_opencode_experiment   --n "$N_HOTPOT" --timeout "$T_SHORT" --port 8830 --runs-dir "${RUN}/mimo_hotpot"
  cell mimo_swebench "mimo_swebench/results.json" \
    $PY -m bench.swebench_opencode_experiment --n "$N_SWE"    --timeout "$T_SWE"   --port 8830 --runs-dir "${RUN}/mimo_swebench"
  cell mimo_nqa      "mimo_longdoc/results_narrativeqa.json" \
    $PY -m bench.longdoc_opencode_experiment  --n "$N_NQA"    --timeout "$T_LONG"  --port 8830 --config narrativeqa --runs-dir "${RUN}/mimo_longdoc"
  cell mimo_gov      "mimo_longdoc/results_gov_report.json" \
    $PY -m bench.longdoc_opencode_experiment  --n "$N_GOV"    --timeout "$T_LONG"  --port 8830 --config gov_report  --runs-dir "${RUN}/mimo_longdoc"
  echo "LANE mimo DONE"
}

# ---- LANE: codex (gpt-5.4-mini, ChatGPT OAuth) -- sequential, port 8840 ----
codex_lane () {
  cell codex_hotpot   "codex_hotpot/results.json" \
    $PY -m bench.hotpot_codex_experiment   --n "$N_HOTPOT" --timeout "$T_SHORT" --port 8840 --runs-dir "${RUN}/codex_hotpot"
  cell codex_swebench "codex_swebench/results.json" \
    $PY -m bench.swebench_codex_experiment --n "$N_SWE"    --timeout "$T_SWE"   --port 8840 --runs-dir "${RUN}/codex_swebench"
  cell codex_nqa      "codex_longdoc/results_narrativeqa.json" \
    $PY -m bench.longdoc_codex_experiment  --n "$N_NQA"    --timeout "$T_LONG"  --port 8840 --config narrativeqa --runs-dir "${RUN}/codex_longdoc"
  cell codex_gov      "codex_longdoc/results_gov_report.json" \
    $PY -m bench.longdoc_codex_experiment  --n "$N_GOV"    --timeout "$T_LONG"  --port 8840 --config gov_report  --runs-dir "${RUN}/codex_longdoc"
  echo "LANE codex DONE"
}

# ---- LANE: claude sonnet (Anthropic) -- sequential, port-base 8850 (on/off = 8850/8851) ----
claude_lane () {
  cell claude_swebench "claude_swebench/results.json" \
    $PY -m bench.swebench_claude_experiment --n "$N_SWE" --timeout "$T_SWE" --port-base 8850 --model sonnet --runs-dir "${RUN}/claude_swebench"
  cell claude_nqa      "claude_longdoc/results_narrativeqa.json" \
    $PY -m bench.longdoc_claude_experiment  --n "$N_NQA" --timeout "$T_LONG" --port-base 8850 --model sonnet --config narrativeqa --runs-dir "${RUN}/claude_longdoc"
  cell claude_gov      "claude_longdoc/results_gov_report.json" \
    $PY -m bench.longdoc_claude_experiment  --n "$N_GOV" --timeout "$T_LONG" --port-base 8850 --model sonnet --config gov_report  --runs-dir "${RUN}/claude_longdoc"
  echo "LANE claude DONE"
}

# ---- launch the 3 lanes concurrently; each lane is sequential inside ----
mimo_lane   > "${LOG}/lane_mimo.log"   2>&1 &  PM=$!
codex_lane  > "${LOG}/lane_codex.log"  2>&1 &  PC=$!
claude_lane > "${LOG}/lane_claude.log" 2>&1 &  PL=$!
echo "lanes launched: mimo=$PM codex=$PC claude=$PL" | tee -a "${ABS}/CAMPAIGN.txt"

wait $PM; echo "mimo lane exit=$?"   | tee -a "${ABS}/CAMPAIGN.txt"
wait $PC; echo "codex lane exit=$?"  | tee -a "${ABS}/CAMPAIGN.txt"
wait $PL; echo "claude lane exit=$?" | tee -a "${ABS}/CAMPAIGN.txt"

echo "CAMPAIGN COMPLETE -> ${ABS}" | tee -a "${ABS}/CAMPAIGN.txt"
echo "report: $PY -m bench.campaign_report '${ABS}/**/results*.json'" | tee -a "${ABS}/CAMPAIGN.txt"
