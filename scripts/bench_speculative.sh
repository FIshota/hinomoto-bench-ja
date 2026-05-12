#!/usr/bin/env bash
# bench_speculative.sh — measure llama.cpp speculative decoding speedup.
#
# Single llama-cli session per config (avoids repeated model-load overhead).
# Reads llama_perf_*_print output for clean timing.
#
# Usage:
#   bash bench_speculative.sh baseline             # 3B fp16 alone
#   bash bench_speculative.sh spec_q4_fp16         # Q4 (draft) + fp16 (target)
#   bash bench_speculative.sh spec_q4_q4           # Q4 (draft) + Q4 (target) — sanity
#   bash bench_speculative.sh all                  # run all three

set -uo pipefail

LLAMA_CLI=/home/ryu/projects/llama.cpp/build_cuda/bin/llama-cli
MODEL_DIR=/mnt/d/hinomoto-data/artifacts/ai_3b_v14_merged_hf
M_Q4="$MODEL_DIR/ai_3b_v14.Q4_K_M.gguf"
M_FP16="$MODEL_DIR/ai_3b_v14.fp16.gguf"
M_V1_Q4=/mnt/d/hinomoto-data/artifacts/ai_3b_v1_merged_hf/ai_3b_v1.Q4_K_M.gguf
M_V1_FP16=/mnt/d/hinomoto-data/artifacts/ai_3b_v1_merged_hf/ai_3b_v1.fp16.gguf

PROMPT="日本の四季 (春・夏・秋・冬) のそれぞれの特徴と、 代表的な行事や食べ物を含めて、 文化的背景に触れながら 説明してください。"
N_PREDICT=200
LOG_DIR=/home/ryu/3day_logs
TS=$(date +%Y%m%d_%H%M%S)
CONFIG="${1:-baseline}"

run_baseline() {
    local out="$LOG_DIR/spec_baseline_${TS}.log"
    echo "[bench] baseline: 3B fp16 alone, n_predict=$N_PREDICT"
    "$LLAMA_CLI" \
        -m "$M_FP16" \
        -ngl 99 \
        -n "$N_PREDICT" \
        --temp 0.0 --top-k 1 \
        --single-turn --no-display-prompt \
        -p "$PROMPT" 2>&1 | tee "$out"
    echo ""
    echo "=== baseline summary ==="
    grep -E "llama_perf|tokens/s|eval_time|prompt_eval" "$out" | head -10
}

run_spec() {
    local draft="$1"
    local target="$2"
    local label="$3"
    local out="$LOG_DIR/spec_${label}_${TS}.log"
    echo "[bench] spec: draft=$(basename $draft) target=$(basename $target), n_predict=$N_PREDICT"
    "$LLAMA_CLI" \
        -m "$target" \
        -md "$draft" \
        -ngl 99 \
        -ngld 99 \
        -n "$N_PREDICT" \
        --temp 0.0 --top-k 1 \
        --spec-draft-n-max 8 \
        --spec-draft-p-min 0.75 \
        --single-turn --no-display-prompt \
        -p "$PROMPT" 2>&1 | tee "$out"
    echo ""
    echo "=== $label summary ==="
    grep -E "llama_perf|tokens/s|eval_time|accept|draft" "$out" | head -15
}

case "$CONFIG" in
    baseline)
        run_baseline
        ;;
    spec_q4_fp16)
        run_spec "$M_Q4" "$M_FP16" "q4_draft_fp16_target"
        ;;
    spec_q4_q4)
        run_spec "$M_Q4" "$M_Q4" "q4_draft_q4_target"
        ;;
    spec_v1q4_v14fp16)
        run_spec "$M_V1_Q4" "$M_FP16" "v1q4_draft_v14fp16_target"
        ;;
    spec_v1q4_v14q4)
        run_spec "$M_V1_Q4" "$M_Q4" "v1q4_draft_v14q4_target"
        ;;
    all)
        run_baseline
        echo ""
        echo "----------------------------------------"
        run_spec "$M_Q4" "$M_FP16" "q4_draft_fp16_target"
        echo ""
        echo "----------------------------------------"
        run_spec "$M_Q4" "$M_Q4" "q4_draft_q4_target"
        ;;
    *)
        echo "Usage: $0 {baseline|spec_q4_fp16|spec_q4_q4|all}" >&2
        exit 2
        ;;
esac
