# 🌅 HinoMoto-Bench-ja v0.2

**Japanese cultural-axis evaluation benchmark for LLMs.**

家族の温かさ・敬語階層・沈黙判断 を測る、日本語 LLM 向け文化軸評価ベンチ.

| Section | Items | Evaluation |
|---|---:|---|
| `data/family.jsonl` | **110** | 家族会話: 共感 / 適切性 / 自然さ / 温度感 (rubric 0-12) |
| `data/keigo.jsonl` | **70** | 敬語階層 (尊敬/謙譲/丁寧/タメ口) 適切性 (pass/fail) |
| `data/silence.jsonl` | **50** | 沈黙判断 (短い高確信度回答, `<silence>`含み) (pass/fail) |
| **Total** | **230** | |

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
| v0.2 | **230** | 2026-05 | 拡張版 + 5-quant baseline reference |
| v0.3 (planned) | 500+ | — | LLM-as-Judge / 人手 score / 多 rater |

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
- [HinoMoto-100M v15 (research)](https://huggingface.co/FiShota/hinomoto-100m-v15-wsd-zloss-ema)
- [HinoMoto-100M v12 (research)](https://huggingface.co/FiShota/hinomoto-100m-v12-wsd-zloss-seed2)

---

**Repository**: https://github.com/FIshota/hinomoto-bench-ja (公開予定)
**Maintainer**: ryu (FIshota)
**Initial release**: 2026-05
