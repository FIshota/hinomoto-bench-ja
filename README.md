# 🌅 HinoMoto-Bench-ja v0.6

**Japanese cultural-axis evaluation benchmark for LLMs.**

家族・敬語・沈黙 + 世代間ギャップ + 職場 + 思いやり / 地方文化 / ニュアンス を測る、日本語 LLM 向け文化軸評価ベンチ. **v0.6 で合成データ拡張により 8 軸合計 692 items (前比 +239) に拡大**.

## ⭐ v0.6 highlights (2026-05-11)

- **8 軸合計 692 items** (v0.5 比 +239 items / +52.8%)
- 軸間バランス改善: local_culture / nuance / generation_gap / workplace が 10 → 40+ items に
- 合成生成 (HinoMoto-3B-Q4 self-generation) + 自動 firewall + manual audit pass
- 詳細生成方法: [docs/SYNTH_V06_GENERATION.md](docs/SYNTH_V06_GENERATION.md)

| Axis | v0.5 | **v0.6 total** | (内訳) |
|---|---:|---:|---|
| family | 130 | **225** | seed 130 + synth 95 |
| keigo | 80 | **107** | seed 80 + synth 27 |
| silence | 70 | **134** | seed 70 + synth 64 |
| compassion | 15 | **62** | seed 15 + synth 47 |
| local_culture | 10 | **42** | seed 10 + synth 32 |
| nuance | 10 | **40** | seed 10 + synth 30 |
| generation_gap | 10 | **40** | seed 10 + synth 30 |
| workplace | 10 | **42** | seed 10 + synth 32 |
| **計 (8 文化軸)** | **335** | **692** | seed 335 + synth 357 |

## v0.6 ファイル構成

| Section | Items | Evaluation |
|---|---:|---|
| `data/bench_v06_full.jsonl` ⭐ NEW v0.6 (統合) | **692** | 8 軸統合マスター (axis フィールドでフィルタ可) |
| `data/bench_v06_<axis>.jsonl` × 8 | — | 軸ごと分割版 (drop-in 評価用) |
| `data/bench_v06_additions.jsonl` ⭐ NEW v0.6 | **357** | v0.5 以降に追加された合成生成分のみ (audit clean 済) |
| `data/family.jsonl` + `_v03_additions.jsonl` | 130 | 家族会話 seed (v0.1 + v0.3) |
| `data/keigo.jsonl` + `_v03_additions.jsonl` | 80 | 敬語階層 seed (v0.1 + v0.3) |
| `data/silence.jsonl` + `_v04_additions.jsonl` | 70 | 沈黙判断 seed (v0.1 + v0.4) |
| `data/compassion_v05.jsonl` | 15 | 思いやり seed (v0.5) |
| `data/local_culture_v05.jsonl` | 10 | 地方文化 seed (v0.5) |
| `data/nuance_v05.jsonl` | 10 | ニュアンス seed (v0.5) |
| `data/generation_gap_v04.jsonl` | 10 | 世代差 seed (v0.4) |
| `data/workplace_v04.jsonl` | 10 | 職場 seed (v0.4) |
| `data/yamato_legal.jsonl` + `_v02.jsonl` + `_v02_additions.jsonl` | 60 | 法律 Q&A (Yamato 軸) |
| `data/4axes_v02_extended.jsonl` | 35 | 7 軸 × 5 問 |
| `data/ethics_v01.jsonl` | 43 | 倫理単軸 |
| **8 文化軸 total (bench_v06_full)** | **692** | |
| **Grand total (Yamato + 4axes + ethics 含む)** | **830** | |

License: **CC BY 4.0** (data) / **MIT** (scripts)

---

## なぜ HinoMoto-Bench-ja?

既存 JP LLM bench (JGLUE / ELYZA-tasks-100 / JMT-Bench / JMMLU 等) は **知識・推論寄り**.
日本語の文化的本質 — 家族関係の温度、敬語の階層、沈黙の含み — を測る軸が **不在**.

本 bench は **CC BY 4.0 で先に公開** し、日本語 LLM 評価の **文化軸標準** として残すことを目指す.

---

## Quick Start

```bash
git clone https://github.com/FIshota/hinomoto-bench-ja.git
cd hinomoto-bench-ja

# 1. Generate responses with your model
#    (your script should produce JSONL with {"id": "<item-id>", "response": "..."})
python your_inference.py \
  --bench data/family.jsonl \
  --out my_model_responses/family.jsonl

# 2. Score with evaluator_v2.py
python scripts/evaluator_v2.py \
  --bench data/family.jsonl \
  --responses my_model_responses/family.jsonl \
  --out my_model_responses/family_scores.json
```

Score JSON example:
```json
{
  "summary": {
    "n": 110, "mean_total": 8.34, "max_possible": 12, "degenerate_rate": 0.0
  },
  "details": [...]
}
```

---

## Bench item format

### `family.jsonl` (rubric scoring 0-12)
```json
{
  "id": "fam-001",
  "category": "morning",
  "context": "平日の朝、子供（小学生）を起こす場面",
  "user": "(まだ眠そう) おはよう...",
  "expected_qualities": ["優しい起床促し", "焦らせない", "温かい声かけ"],
  "anti_patterns": ["長文説教", "冷たい指示", "詰問"],
  "ideal_response_example": "おはよう。顔洗ってきなよ",
  "rubric": {
    "empathy": "...", "appropriateness": "...",
    "naturalness": "...", "warmth": "..."
  }
}
```

### `keigo.jsonl` (pass/fail)
```json
{
  "id": "kg-001",
  "context": "上司との会議",
  "user": "資料を確認しましたか?",
  "expected_register": "丁寧 + 謙譲",
  "must_contain": ["拝見", "ご確認"],
  "anti_patterns": ["タメ口"]
}
```

### `silence.jsonl` (pass/fail)
```json
{
  "id": "sl-001",
  "context": "親しい家族の悲しい話を聞いた直後",
  "user": "本当につらかった...",
  "expected": "短い相槌または無言",
  "anti_patterns": ["長文助言", "明るい話題転換"]
}
```

---

## Reference baselines

`results/baseline/` に **HinoMoto-Sarashina2.2-3B-sft_v3** (4-quant × 3-seed × 3-axis = 45 score files) を同梱.
量子化と task の関係を示す重要な reference データ.

> Note: baseline モデルは内部 SFT 名を学習していたため、`*_responses_seed*.jsonl` 中の出力で内部識別子に該当する箇所は `私` に置換しています (出力件数・採点には影響なし).

### Summary table (3-seed mean ± std, n=各 task)

| Variant | BPW | family /12 | keigo % | silence % |
|---|---:|---:|---:|---:|
| Q6_K | 6.60 | 8.10 ± 0.17 | 33.3 ± 5.8 | 31.3 ± 4.2 |
| Q5_K_M | 5.72 | 8.28 ± 0.10 | 32.4 ± 4.4 | 38.7 ± 5.0 |
| Q4_K_M | 4.92 | 8.25 ± 0.22 | 31.9 ± 4.1 | 29.3 ± 3.1 |
| **Q3_K_M** ⭐ | **3.91** | **8.00 ± 0.16** | **32.9 ± 3.8** | **42.0 ± 3.5** |

**Counter-intuitive finding**: Q3_K_M (smallest, 1.6 GB) achieves the **best silence-axis score**.
Quantization is **task-dependent** — bit count alone does not determine quality.

→ Detailed analysis: see [HinoMoto-3B HF Hub repo](https://huggingface.co/FiShota/sarashina2.2-3b-sft-v3-Q4_K_M-gguf).

---

## Evaluation methodology

### Auto (CI で回せる)
- `evaluator_v2.py` で 3 task 全部 score 化
- rubric matching + must_contain / anti_pattern check
- degenerate_rate (繰り返し / 空応答 検出) も同時計測

### Optional human grading
- 家族 5 人による blind 採点 (model 名隠し) を推奨
- 自動 score との Pearson r を測ると信頼性向上

### LLM-as-a-Judge
- GPT-4 / Claude にrubric を渡して採点する evaluator (TBD v0.3)
- 複数 judge 平均で stochastic noise 軽減

---

## Decontamination

`decontamination_report.json`: bench items が public corpus (CC100 / OSCAR / Diet records / Aozora) と
n-gram overlap していないことを確認した report. **訓練データには本 bench を含めないこと**.

---

## Versioning

| Version | Items | Date | Notes |
|---|---:|---|---|
| v0.1 | 50 | 2026-04 | 叩き台 (家族 25 + 敬語 15 + 沈黙 10) |
| v0.2 | 230 | 2026-05 | 拡張版 + 5-quant baseline reference |
| v0.2.1 | 348 | 2026-05-09 | +Yamato 法律 v02 追加分 / +4axes v02 拡張 / +ethics v01 + 内部識別子の redaction |
| v0.3 | 378 | 2026-05-09 | +family v03 (20) + keigo v03 (10) — 朝夜週末/ビジネス場面拡充 |
| v0.4 | 418 | 2026-05-09 | +silence v04 (20) + 新軸 generation_gap (10) + 新軸 workplace (10) |
| **v0.5** | **453** | **2026-05-10** | +新軸 compassion (15) + 新軸 local_culture (10) + 新軸 nuance (10) |
| v0.6 (planned) | 600+ | — | LLM-as-Judge / 人手 score / 多 rater / 4-quant baseline rerun |

---

## Citation

```bibtex
@misc{hinomoto-bench-ja-2026,
  author = {ryu (FiShota)},
  title = {HinoMoto-Bench-ja: Japanese cultural-axis evaluation benchmark for LLMs},
  year = {2026},
  url = {https://github.com/FIshota/hinomoto-bench-ja}
}
```

## License

- **Data** (`data/*.jsonl`): CC BY 4.0
- **Scripts** (`scripts/*.py`): MIT
- **Reference baselines** (`results/baseline/*`): MIT (HinoMoto sft_v3 model output)

## Related

- [HinoMoto-3B sft_v3 GGUF (4 quants)](https://huggingface.co/FiShota/sarashina2.2-3b-sft-v3-Q4_K_M-gguf) — multi-quant baseline
- [HinoMoto-3B sft_v4 GGUF (4 quants)](https://huggingface.co/FiShota/sarashina2.2-3b-sft-v4-gguf) — sft_v3 + 11% NLI replay
- [HinoMoto-3B sft_v4-DPO GGUF](https://huggingface.co/FiShota/sarashina2.2-3b-sft-v4-dpo-gguf) — sft_v4 + DPO 108 pairs (2026-05)
- [Yamato-3B-v1 legal GGUF](https://huggingface.co/FiShota/yamato-3b-v1-legal-gguf) — 法律/行政 specialist sister model (50 SFT samples)
- **[Yamato-3B-v2 legal GGUF](https://huggingface.co/FiShota/yamato-3b-v2-legal-gguf)** ⭐ — Yamato v2 (60 samples + 10 new legal domains, 2026-05 latest)
- [HinoMoto-100M v15 (research)](https://huggingface.co/FiShota/hinomoto-100m-v15-wsd-zloss-ema)
- [HinoMoto-100M v12 (research)](https://huggingface.co/FiShota/hinomoto-100m-v12-wsd-zloss-seed2)

---

**Repository**: https://github.com/FIshota/hinomoto-bench-ja (公開予定)
**Maintainer**: ryu (FIshota)
**Initial release**: 2026-05
