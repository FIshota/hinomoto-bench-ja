#!/usr/bin/env bash
# Quick smoke test of synth_data_gen_v2.py on one axis.
# Usage: bash synth_v2_smoke.sh <axis> [target_n]
# Example: bash synth_v2_smoke.sh compassion 5

set -euo pipefail

AXIS=${1:?Usage: $0 <axis> [target_n]}
TARGET=${2:-5}
LOG=${LOG:-/home/ryu/3day_logs/synth_v2_smoke_${AXIS}.log}

cd /home/ryu/projects/hinomoto-bench-ja
source .venv/bin/activate 2>/dev/null || true

# Resolve seed file (try _v05, _v04_additions, _v04, _v03_additions, plain)
SEED=""
for cand in \
    "data/${AXIS}_v05.jsonl" \
    "data/${AXIS}_v04_additions.jsonl" \
    "data/${AXIS}_v04.jsonl" \
    "data/${AXIS}_v03_additions.jsonl" \
    "data/${AXIS}.jsonl"; do
    if [[ -s "$cand" ]]; then
        SEED="$cand"
        break
    fi
done
if [[ -z "$SEED" ]]; then
    echo "[smoke] no seed found for axis=$AXIS"
    exit 2
fi

OUT="data/${AXIS}_smoke_v2.jsonl"
echo "[smoke] axis=$AXIS seed=$SEED target=$TARGET out=$OUT" | tee "$LOG"

python3 scripts/synth_data_gen_v2.py \
    --bench "$SEED" \
    --output "$OUT" \
    --axis "$AXIS" \
    --smoke-n "$TARGET" \
    --n-per-seed 3 \
    --retries 3 \
    --cycles 4 \
    --temperature 0.85 \
    --log-level INFO 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
ACTUAL=$(wc -l < "$OUT" 2>/dev/null || echo 0)
echo "[smoke] result: $ACTUAL / $TARGET items in $OUT" | tee -a "$LOG"
if [[ "$ACTUAL" -gt 0 ]]; then
    echo "[smoke] sample:" | tee -a "$LOG"
    head -1 "$OUT" | python3 -c "import sys, json; print(json.dumps(json.loads(sys.stdin.read()), ensure_ascii=False, indent=2))" 2>&1 | head -30 | tee -a "$LOG"
fi
