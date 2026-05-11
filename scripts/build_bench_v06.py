"""Build bench v06 by combining existing axis files + cleaned synth additions.

Output structure:
  bench_v06_full.jsonl    — single file with all axes, items tagged by axis
  bench_v06_<axis>.jsonl  — per-axis files (drop-in replacement for current files)

Tags `source`: "v05_seed" (pre-existing) or "v06_synth" (new generation).
Existing items keep their original schema (id, category, rubric, etc.).
New synth items get axis-prefixed IDs and minimal rubric template.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

DATA = Path("/home/ryu/projects/hinomoto-bench-ja/data")

# axis -> list of (seed_file, source_tag)
AXIS_SEEDS = {
    "family": [
        ("family.jsonl", "v01_seed"),
        ("family_v03_additions.jsonl", "v03_seed"),
    ],
    "keigo": [
        ("keigo.jsonl", "v01_seed"),
        ("keigo_v03_additions.jsonl", "v03_seed"),
    ],
    "silence": [
        ("silence.jsonl", "v01_seed"),
        ("silence_v04_additions.jsonl", "v04_seed"),
    ],
    "compassion": [
        ("compassion_v05.jsonl", "v05_seed"),
    ],
    "local_culture": [
        ("local_culture_v05.jsonl", "v05_seed"),
    ],
    "nuance": [
        ("nuance_v05.jsonl", "v05_seed"),
    ],
    "generation_gap": [
        ("generation_gap_v04.jsonl", "v04_seed"),
    ],
    "workplace": [
        ("workplace_v04.jsonl", "v04_seed"),
    ],
}

# Default rubric template per axis (used when synth items have no rubric)
AXIS_RUBRIC = {
    "family": {
        "warmth": "家族らしい温度感が伝わるか",
        "appropriateness": "場面に合った言葉か",
        "naturalness": "親しい関係性で違和感なく使われるか",
    },
    "keigo": {
        "formality": "敬語の使い分け (尊敬・謙譲・丁寧) が正しいか",
        "context_fit": "場面 (社内・社外・公的) に合った敬意レベルか",
        "naturalness": "硬すぎず軟らかすぎず",
    },
    "silence": {
        "restraint": "言葉を選ぶより黙る価値を尊重しているか",
        "respect": "相手の感情/尊厳を踏みにじっていないか",
        "tone": "短い言葉でも温度があるか",
    },
    "compassion": {
        "empathy": "相手の状況/感情への共感があるか",
        "distance": "押し付けず適切な距離感か",
        "naturalness": "業務的でなく自然な寄り添いか",
    },
    "local_culture": {
        "cultural_awareness": "地方文化/慣習を理解しているか",
        "appropriateness": "場面 (冠婚葬祭・茶道など) に合った所作/言葉か",
    },
    "nuance": {
        "implication_understanding": "言外の意味を読み取れているか",
        "appropriateness": "場面に合った返答か",
    },
    "generation_gap": {
        "generational_sensitivity": "世代差への気遣いがあるか",
        "patience": "焦らせず説明できるか",
    },
    "workplace": {
        "professionalism": "業務的に適切か",
        "consideration": "相手の立場/感情への配慮があるか",
        "boundary": "場面の境界を保てているか",
    },
}


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    items = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items


def main():
    per_axis_items: dict[str, list[dict]] = defaultdict(list)
    seen_keys: set[tuple[str, str]] = set()  # (axis, ctx|user)
    counts = Counter()

    # 1. Load existing seeds for each axis
    for axis, seed_files in AXIS_SEEDS.items():
        for fname, src in seed_files:
            items = load_jsonl(DATA / fname)
            for it in items:
                # Force-normalize axis name (some seeds use old labels like
                # "generation" instead of canonical "generation_gap")
                it["axis"] = axis
                it["source"] = src
                key = (axis, str(it.get("context", "")) + "|" + str(it.get("user", "")))
                if key in seen_keys:
                    counts["dedup_seed"] += 1
                    continue
                seen_keys.add(key)
                per_axis_items[axis].append(it)
                counts[f"{axis}_{src}"] += 1

    # 2. Load cleaned synth additions
    additions = load_jsonl(DATA / "bench_v06_additions.jsonl")
    for it in additions:
        axis = it.get("axis", "unknown")
        it["source"] = "v06_synth"
        # Add rubric template if missing
        if "rubric" not in it and axis in AXIS_RUBRIC:
            it["rubric"] = AXIS_RUBRIC[axis]
        # Cross-axis dedup
        key = (axis, str(it.get("context", "")) + "|" + str(it.get("user", "")))
        if key in seen_keys:
            counts["dedup_synth"] += 1
            continue
        seen_keys.add(key)
        per_axis_items[axis].append(it)
        counts[f"{axis}_v06_synth"] += 1

    # 3. Write per-axis files + master file
    master_path = DATA / "bench_v06_full.jsonl"
    total = 0
    print(f"{'axis':<18} {'items':>6}  per_source")
    print("-" * 80)
    with master_path.open("w", encoding="utf-8") as mfh:
        for axis in AXIS_SEEDS.keys():
            items = per_axis_items.get(axis, [])
            # Re-tag with stable axis-relative IDs (preserve original IDs as orig_id)
            for i, it in enumerate(items):
                if "id" in it:
                    it["orig_id"] = it["id"]
                it["id"] = f"v06-{axis}-{i:04d}"
                mfh.write(json.dumps(it, ensure_ascii=False) + "\n")
            # Also per-axis file
            per_axis_path = DATA / f"bench_v06_{axis}.jsonl"
            with per_axis_path.open("w", encoding="utf-8") as pfh:
                for it in items:
                    pfh.write(json.dumps(it, ensure_ascii=False) + "\n")
            # Per-source breakdown
            src_counts = Counter(it.get("source", "?") for it in items)
            src_str = " ".join(f"{k}={v}" for k, v in sorted(src_counts.items()))
            print(f"{axis:<18} {len(items):>6}  {src_str}")
            total += len(items)

    print("-" * 80)
    print(f"{'TOTAL':<18} {total:>6}")
    print()
    print(f"master file: {master_path}")
    print(f"dedup hits during merge: seed={counts.get('dedup_seed', 0)} synth={counts.get('dedup_synth', 0)}")


if __name__ == "__main__":
    main()
