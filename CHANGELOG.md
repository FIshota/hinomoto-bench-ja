# Changelog

All notable changes to HinoMoto-Bench-ja.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v0.6] — 2026-05-12

### Added
- **Self-generation pipeline**: `scripts/synth_data_gen_v2.py` — per-seed retry × cycles with tolerant JSON parser
- **357 new items** across all 8 cultural axes via 3B-class LLM self-generation
- `scripts/cleanup_merge_synth.py` — placeholder/artifact filter (8.9% drop rate)
- `scripts/build_bench_v06.py` — seed + synth merger with per-axis stratification
- `scripts/audit_synth_v06.py` — schema + firewall + dedup audit
- `scripts/eval_cultural_sft_smoke.py` — SFT adapter eval harness
- `scripts/compare_base_vs_sft.py` — base vs SFT quantitative comparison
- `scripts/split_bench_v06_for_sft.py` — 80/20 stratified split for SFT
- `scripts/bench_speculative.sh` — llama.cpp speculative decoding bench
- `data/bench_v06_full.jsonl` — 692 items consolidated master file
- `data/bench_v06_<axis>.jsonl` × 8 — per-axis split files
- `data/bench_v06_additions.jsonl` — clean synth additions only (357 items)
- `data/bench_v06_sft_train.jsonl` / `_eval.jsonl` — 80/20 SFT split (551/141)
- `docs/SYNTH_V06_GENERATION.md` — methodology doc with failure lessons

### Changed
- **Items**: 453 → **692** (+239, +52.8%)
- Axis balance: small axes (10) expanded to 30-65 items each
- README updated with v0.6 axis table + cumulative changelog

### Per-axis growth (v0.5 → v0.6)

| Axis | v0.5 | v0.6 | growth |
|---|---:|---:|---:|
| family | 130 | 225 | +73% |
| keigo | 80 | 107 | +34% |
| silence | 70 | 134 | +91% |
| compassion | 15 | 62 | **+313%** |
| local_culture | 10 | 42 | **+320%** |
| nuance | 10 | 40 | **+300%** |
| generation_gap | 10 | 40 | **+300%** |
| workplace | 10 | 42 | **+320%** |
| **計** | **335** | **692** | **+107%** |

### Quality

- Audit clean: 692/692 schema valid, 0 firewall hits, 0 cross-axis duplicates
- SFT validation: Cultural SFT on 551 train items → mean_token_accuracy 86.8%, base 109 chars → SFT 20 chars output length

---

## [v0.5] — 2026-05-09

### Added
- New axes: compassion (15), local_culture (10), nuance (10)
- `data/compassion_v05.jsonl`, `data/local_culture_v05.jsonl`, `data/nuance_v05.jsonl`

### Changed
- Items: 418 → 453

---

## [v0.4] — 2026-05-08

### Added
- New axes: silence_v04_additions (20), generation_gap (10), workplace (10)

### Changed
- Items: 378 → 418

---

## [v0.3] — 2026-05-05

### Added
- family_v03_additions (20), keigo_v03_additions (10)

### Changed
- Items: 230 → 378

---

## [v0.2.1] — 2026-05-04

### Added
- Bench expansion + privacy redaction sweep

---

## [v0.2] — 2026-05-03 (initial release)

### Added
- 230 items across 4 base axes (family, keigo, silence) + 5-quant Yamato baseline
- evaluator_v2.py
- scripts/bench_yamato_*.py

---

## License

Data: **CC BY 4.0**
Scripts: **MIT**

Maintained by ryu (FIshota). Issues/PRs welcome at https://github.com/FIshota/hinomoto-bench-ja
