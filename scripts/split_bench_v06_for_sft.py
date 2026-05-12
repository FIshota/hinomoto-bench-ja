"""Split bench_v06_full.jsonl into 80/20 train/eval for #4 cultural-axis SFT.

Stratified by axis (each axis gets same 80/20 ratio).
Output:
  data/bench_v06_sft_train.jsonl
  data/bench_v06_sft_eval.jsonl
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path("/home/ryu/projects/hinomoto-bench-ja/data")
SEED = 2026
TRAIN_RATIO = 0.80

AXIS_DEFS = {
    "family": "家族関係 (親・配偶者・子・兄弟・祖父母)",
    "keigo": "敬語 (尊敬・謙譲・丁寧) の使い分け",
    "silence": "沈黙判断 (言葉より黙る価値)",
    "compassion": "他者への思いやり (弱者支援・寄り添い・距離感)",
    "local_culture": "地方文化・慣習 (京都・東北・冠婚葬祭)",
    "nuance": "日本語の言外の意味 (結構です・遠回しの断り)",
    "generation_gap": "祖父母↔孫 / 親↔若者 の世代差",
    "workplace": "職場 (上司部下・退職・ハラスメント・メンタル)",
}


def make_sft_pair(item: dict) -> dict:
    """Convert bench item to SFT prompt/response pair."""
    axis = item.get("axis", "")
    ctx = item.get("context", "")
    user = item.get("user", "")
    ire = item.get("ideal_response_example", "")
    axis_def = AXIS_DEFS.get(axis, "")

    prompt_lines = []
    prompt_lines.append(f"{axis}軸: {axis_def}")
    prompt_lines.append(f"場面: {ctx}")
    if user and user.strip():
        prompt_lines.append(f"ユーザー発言: {user}")
    prompt_lines.append("回答:")
    prompt = "\n".join(prompt_lines)

    return {
        "id": item.get("id"),
        "axis": axis,
        "source": item.get("source", "?"),
        "prompt": prompt,
        "response": ire,
    }


def main():
    in_path = DATA / "bench_v06_full.jsonl"
    if not in_path.exists():
        print(f"ERROR: {in_path} not found", file=sys.stderr)
        return 1

    # Group by axis
    by_axis: dict[str, list[dict]] = defaultdict(list)
    with in_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                it = json.loads(line)
                by_axis[it.get("axis", "unknown")].append(it)

    # Stratified split
    rng = random.Random(SEED)
    train_items: list[dict] = []
    eval_items: list[dict] = []
    print(f"{'axis':<18} {'total':>6} {'train':>6} {'eval':>5}")
    print("-" * 45)
    for axis, items in sorted(by_axis.items()):
        rng.shuffle(items)
        cut = int(len(items) * TRAIN_RATIO)
        train_items.extend(items[:cut])
        eval_items.extend(items[cut:])
        print(f"{axis:<18} {len(items):>6} {cut:>6} {len(items)-cut:>5}")
    print("-" * 45)
    print(f"{'TOTAL':<18} {len(train_items)+len(eval_items):>6} {len(train_items):>6} {len(eval_items):>5}")

    # Write SFT-formatted output
    train_path = DATA / "bench_v06_sft_train.jsonl"
    eval_path = DATA / "bench_v06_sft_eval.jsonl"
    eval_meta_path = DATA / "bench_v06_sft_eval_full.jsonl"  # keep full bench fields too

    with train_path.open("w", encoding="utf-8") as fw:
        for it in train_items:
            fw.write(json.dumps(make_sft_pair(it), ensure_ascii=False) + "\n")

    with eval_path.open("w", encoding="utf-8") as fw:
        for it in eval_items:
            fw.write(json.dumps(make_sft_pair(it), ensure_ascii=False) + "\n")

    # Also keep eval items in original bench format (for evaluator_v3.py use)
    with eval_meta_path.open("w", encoding="utf-8") as fw:
        for it in eval_items:
            fw.write(json.dumps(it, ensure_ascii=False) + "\n")

    print()
    print(f"SFT format: {train_path}")
    print(f"SFT format: {eval_path}")
    print(f"Bench format (eval only): {eval_meta_path}")
    print()
    print("# Sample SFT pair")
    if train_items:
        print(json.dumps(make_sft_pair(train_items[0]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main() or 0)
