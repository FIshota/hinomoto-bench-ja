#!/usr/bin/env bash
# synth_all_axes_v2.sh — v2 synth pipeline for all 8 bench axes.
# Uses synth_data_gen_v2.py (per-seed retry, cycles, axis hints, tolerant parser).
#
# Per-axis params tuned to seed-pool size:
#   - large pools (family 110, keigo 70, silence 50): cycles=2, target 100
#   - mid pool (compassion 15): cycles=6, target 50
#   - small pools (10 each): cycles=8, target 35
#
# Usage:
#   bash synth_all_axes_v2.sh              # default targets
#   bash synth_all_axes_v2.sh --skip-done  # skip axes with output > 30 items
set -uo pipefail

DATA=/home/ryu/projects/hinomoto-bench-ja/data
SCRIPT=/home/ryu/projects/hinomoto-bench-ja/scripts/synth_data_gen_v2.py
PY=/usr/bin/python3
LOG_DIR=/home/ryu/3day_logs
TS=$(date +%Y%m%d_%H%M%S)

SKIP_DONE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-done) SKIP_DONE=1; shift ;;
        *)           echo "[axes_v2] unknown arg: $1" >&2; exit 2 ;;
    esac
done

# axis -> "seed_file:target:cycles"
declare -A AXES=(
    [family]="family.jsonl:100:2"
    [keigo]="keigo.jsonl:100:2"
    [silence]="silence.jsonl:100:3"
    [compassion]="compassion_v05.jsonl:50:6"
    [local_culture]="local_culture_v05.jsonl:35:8"
    [nuance]="nuance_v05.jsonl:35:8"
    [generation_gap]="generation_gap_v04.jsonl:35:8"
    [workplace]="workplace_v04.jsonl:35:8"
)

echo "[axes_v2] start ts=$TS skip_done=$SKIP_DONE"

for axis in family keigo silence compassion local_culture nuance generation_gap workplace; do
    spec=${AXES[$axis]}
    IFS=':' read -r seed_file target cycles <<< "$spec"

    out="$DATA/${axis}_synth_v06.jsonl"
    seed_path="$DATA/$seed_file"

    if [[ ! -s "$seed_path" ]]; then
        echo "[axes_v2] SKIP $axis — seed not found: $seed_path"
        continue
    fi

    current=$(wc -l < "$out" 2>/dev/null || echo 0)
    if [[ "$SKIP_DONE" == "1" && "$current" -ge 30 ]]; then
        echo "[axes_v2] SKIP $axis — already has $current items (>= 30)"
        continue
    fi

    log="$LOG_DIR/49_synth_v2_${axis}_${TS}.log"
    echo ""
    echo "[axes_v2] === $axis === seed=$seed_file target=$target cycles=$cycles current=$current"
    echo "[axes_v2] log=$log"

    $PY "$SCRIPT" \
        --bench "$seed_path" \
        --output "$out" \
        --axis "$axis" \
        --n-per-seed 3 \
        --retries 3 \
        --cycles "$cycles" \
        --temperature 0.85 \
        --max-output "$target" \
        --log-level INFO 2>&1 | tee "$log"

    new_count=$(wc -l < "$out" 2>/dev/null || echo 0)
    echo "[axes_v2] $axis done: $new_count items"
done

echo ""
echo "[axes_v2] === final inventory ==="
total=0
for axis in family keigo silence compassion local_culture nuance generation_gap workplace; do
    out="$DATA/${axis}_synth_v06.jsonl"
    count=$(wc -l < "$out" 2>/dev/null || echo 0)
    total=$((total + count))
    printf "  %-18s %4d items\n" "$axis" "$count"
done
printf "  %-18s %4d items\n" "TOTAL" "$total"
echo "[axes_v2] complete"
