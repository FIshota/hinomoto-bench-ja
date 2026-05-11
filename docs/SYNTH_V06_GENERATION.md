# Synthetic data generation for HinoMoto-Bench v0.6

This document describes the methodology used to expand HinoMoto-Bench-ja from 453 → 692 items by self-generation with HinoMoto-3B-Q4.

## 概要

- **生成器**: HinoMoto-3B (= ai_3b_v14, 3B params Q4_K_M GGUF) on local llama.cpp server
- **目的**: 軸間 item 数のバランス改善 (小軸 10 items → 30-65 items に拡大)
- **手法**: seed-based expansion (各 v0.5 seed を 1 例として、 同軸内で別場面の項目を生成)
- **品質保証**: tolerant JSON parser + schema validate + placeholder filter + firewall

## 数値

### 生成 → クリーンアップ

| Axis | 生成 raw | clean 後 | drop 率 |
|---|---:|---:|---:|
| family | 100 | 95 | 5.0% |
| keigo | 31 | 27 | 12.9% |
| silence | 71 | 64 | 9.9% |
| compassion | 50 | 47 | 6.0% |
| local_culture | 35 | 32 | 8.6% |
| nuance | 35 | 30 | 14.3% |
| generation_gap | 35 | 30 | 14.3% |
| workplace | 35 | 32 | 8.6% |
| **合計** | **392** | **357** | **8.9%** |

### Drop 理由内訳 (合計 35 items)

| reason | count | 説明 |
|---|---:|---|
| `eq-placeholder` | 16 | `expected_qualities` に `...` 等の placeholder leakage |
| `ire-artifact` | 10 | `ideal_response_example` に backtick / 英語混入等の artifact |
| `ap-placeholder` | 9 | `anti_patterns` の placeholder |

## 生成パラメータ (synth_data_gen_v2.py)

```python
payload = {
    "model": "ai_3b_v14.Q4_K_M.gguf",
    "max_tokens": 2000,
    "temperature": 0.85,  # +0.10 ramp per retry; +0.05 ramp per cycle
    "top_p": 0.9,
    "repeat_penalty": 1.05,  # 重要: JSON 構造 token を罰しすぎないため低め
    "stop": ["</em>", "</p>", "</s>", "<|im_end|>",
             "...........", "。。。。。"],
}
```

## 軸ごとの per-axis spec (synth_all_axes_v2.sh)

| Axis | seed pool | target | cycles | acceptance | 所要 |
|---|---:|---:|---:|---:|---:|
| family | 110 | 100 | 2 | ~50% | ~10min |
| keigo | 70 | 100 | 2 | **7.9%** ⚠ | ~17min |
| silence | 50 | 100 | 3 | 17.8% | ~15min |
| compassion | 15 | 50 | 6 | ~40% | ~10min |
| local_culture | 10 | 35 | 8 | ~40% | ~5min |
| nuance | 10 | 35 | 8 | ~40% | ~5min |
| generation_gap | 10 | 35 | 8 | ~40% | ~5min |
| workplace | 10 | 35 | 8 | ~40% | ~5min |

⚠ keigo は 3B model にとって特に難しい軸 (敬語階層・社内/社外区別 等が必要). 全 70 seeds × 2 cycles = 140 試行で 31 items, target 100 に届かず.

## クリーンアップルール (cleanup_merge_synth.py)

drop 条件:
- `expected_qualities` 中に純粋な句読点だけの string (`...`, `?`, etc.) を含む
- 4+ 連続 ASCII 英字を含む文字列 (英語混入 ; 但し `SNS`, `PC`, `LGBTQ` 等は許容)
- backtick で囲まれた segment (model artifact)
- 全角・半角の paren が壊れている
- public firewall 違反 (`ai-chan`, `Ai` 等内部識別子)

## 統合スクリプト (すべて `scripts/` 配下)

1. **`scripts/synth_data_gen_v2.py`** — 1 軸ぶん生成 (seed loop × cycles × retries × n_per_seed)
2. **`scripts/synth_all_axes_v2.sh`** — 8 軸を順次走らせる cascade
3. **`scripts/cleanup_merge_synth.py`** — raw synth output → clean merged additions
4. **`scripts/build_bench_v06.py`** — clean additions + 既存 seeds → bench v0.6 master
5. **`scripts/audit_synth_v06.py`** — 全 v06 出力の audit (firewall / schema / dedup / sample)
6. **`scripts/synth_v2_smoke.sh`** — 1 軸 quick smoke (acceptance rate 検証)

## tolerant JSON parser (parse_response)

5 段階 fallback:

1. 全文 `json.loads` (kosher 入力)
2. 最初の `[...]` ブロック正規抽出 → strict parse
3. 同ブロックに tolerant fix-ups (smart quotes / full-width punct / trailing comma)
4. 全文 fix-up + bracket completion (truncated output recovery)
5. **RESCUE**: 平衡 `{...}` ブロックを個別抽出 (部分的崩壊からも 1-2 items 救出)

追加処理:
- key alias 正規化 (`antipaterns` → `anti_patterns` 等の typo を吸収)
- HTML タグ scrub (`<em>`, `</p>` 等の漏れ除去)
- 全レベル文字列 walk → firewall check

## 失敗から学んだこと (反映済)

- ❌ `json_schema` constrained decoding は 3B model で **trivial output collapse** (`"......"` で最短経路を取る)
- ❌ `repeat_penalty=1.18` (一般推奨) は JSON 構造 token を罰しすぎ → 7% acceptance に低下
- ✅ `repeat_penalty=1.05` + prompt 指示 + tolerant parser で **40-50% acceptance** に改善
- ✅ `stop tokens` は legitimate content と衝突しないか確認必須 (`。。。` は止めるべきではない)

詳細は [DEVELOPMENT_FAILURES_AND_RECOVERY.md](../../docs/DEVELOPMENT_FAILURES_AND_RECOVERY.md) Incident 12-13 を参照.

## 再現コマンド

```bash
# 1. llama-server 起動 (HinoMoto-3B Q4 with -ngl 99)
cd ~/projects/llama.cpp/build_cuda/bin
./llama-server -m /path/to/ai_3b_v14.Q4_K_M.gguf -ngl 99 \
    --port 8092 --host 127.0.0.1 -t 4 -c 4096

# 2. 全 8 軸 cascade (~2h)
cd ~/projects/hinomoto-bench-ja
bash scripts/synth_all_axes_v2.sh

# 3. クリーンアップ + 統合
python3 scripts/cleanup_merge_synth.py
python3 scripts/build_bench_v06.py

# 4. (option) audit を改めて全ファイルに走らせる
python3 scripts/audit_synth_v06.py
```

## License

CC BY 4.0 (data) / MIT (scripts).

Generated 2026-05-11. HinoMoto-Bench-ja maintainer: ryu (FIshota).
