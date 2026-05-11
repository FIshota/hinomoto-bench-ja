#!/usr/bin/env bash
# synth_all_axes.sh — generate synthetic data for all 8 bench axes sequentially.
# Each axis gets ~50-100 items via existing synth_data_gen.py + llama-server.
#
# Strategy: serial (not parallel) to avoid GPU contention on the llama-server.
# Each axis writes to data/<axis>_synth_v06.jsonl
#
# Usage:
#   bash synth_all_axes.sh              # full run (~6-8 hours, BG via nohup recommended)
#   bash synth_all_axes.sh --skip-done  # skip axes that already have output > 50 items
set -uo pipefail

DATA=/home/ryu/projects/hinomoto-bench-ja/data
SCRIPT=/home/ryu/projects/hinomoto-bench-ja/scripts/synth_data_gen.py
PY=/usr/bin/python3
LOG_DIR=/home/ryu/3day_logs

SKIP_DONE=0
[ "${1:-}" = "--skip-done" ] && SKIP_DONE=1

# axis -> (seed file, target count)
declare -A AXES=(
    [family]="family.jsonl 100"
    [keigo]="keigo.jsonl 100"
    [silence]="silence.jsonl 100"
    [compassion]="compassion_v05.jsonl 100"
    [local_culture]="local_culture_v05.jsonl 50"
    [nuance]="nuance_v05.jsonl 50"
    [generation_gap]="generation_gap_v04.jsonl 50"
    [workplace]="workplace_v04.jsonl 50"
)

echo "================================================"
echo "synth_all_axes — $(date '+%F %T')"
echo "================================================"

for axis in family keigo silence compassion local_culture nuance generation_gap workplace; do
    spec="${AXES[$axis]}"
    seed_file=$(echo "$spec" | awk '{print $1}')
    target=$(echo "$spec" | awk '{print $2}')

    seed_path="$DATA/$seed_file"
    out_path="$DATA/${axis}_synth_v06.jsonl"
    log_path="$LOG_DIR/47_synth_${axis}.log"

    if [ ! -f "$seed_path" ]; then
        echo "❌ axis=$axis: seed not found ($seed_path), skip"
        continue
    fi

    # Skip if output exists and looks complete
    if [ "$SKIP_DONE" = "1" ] && [ -f "$out_path" ]; then
        existing=$(wc -l < "$out_path")
        if [ "$existing" -ge "$target" ]; then
            echo "⏩ axis=$axis: existing $existing >= $target, skip"
            continue
        fi
    fi

    echo ""
    echo "▶ axis=$axis: target=$target seeds=$(wc -l < $seed_path) → $out_path"
    "$PY" "$SCRIPT" \
        --bench "$seed_path" \
        --output "$out_path" \
        --n-per-seed 5 \
        --max-output "$target" \
        --axis "$axis" \
        --id-prefix "syn-${axis}" \
        --temperature 0.85 \
        2>&1 | tee "$log_path" | tail -3
    n=$(wc -l < "$out_path" 2>/dev/null || echo 0)
    echo "✓ axis=$axis: $n items written"
done

echo ""
echo "================================================"
echo "all axes complete — $(date '+%F %T')"
echo "================================================"

# Summary
echo ""
echo "Summary:"
total=0
for axis in family keigo silence compassion local_culture nuance generation_gap workplace; do
    out_path="$DATA/${axis}_synth_v06.jsonl"
    if [ -f "$out_path" ]; then
        n=$(wc -l < "$out_path")
        printf "  %-18s %4d items\n" "$axis" "$n"
        total=$((total + n))
    fi
done
echo "  ────────────────────────────"
printf "  %-18s %4d items\n" "TOTAL" "$total"
