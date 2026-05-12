"""Quick eval: SFT adapter vs base on cultural bench_v06 eval split (141 items).

Loads base + adapter, generates responses for eval items, prints a per-axis
sample comparison (no automatic rubric scoring — that's for evaluator_v3.py).

This is a SMOKE eval: 1-2 sample per axis to confirm the adapter learned
something useful. For full eval, use evaluator_v3.py with the generated jsonl.

Usage:
  python eval_cultural_sft_smoke.py \\
      --base /mnt/d/hinomoto-data/artifacts/ai_3b_v14_merged_hf \\
      --adapter /mnt/d/hinomoto-data/artifacts/ai_3b_cultural_sft_v1_r32 \\
      --eval-split data/bench_v06_sft_eval.jsonl \\
      --per-axis 2 \\
      --out cultural_sft_eval_smoke.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logger = logging.getLogger("eval_smoke")


def load_eval(path: Path) -> dict[str, list[dict]]:
    """Group eval items by axis."""
    by_axis: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                it = json.loads(line)
                by_axis[it.get("axis", "unknown")].append(it)
    return by_axis


def generate(model, tok, prompt: str, max_new: int = 100) -> str:
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new,
            do_sample=False,
            temperature=1.0,
            top_k=1,
            pad_token_id=tok.eos_token_id,
        )
    full = tok.decode(out[0], skip_special_tokens=True)
    # Strip the prompt portion
    return full[len(prompt):].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base model dir (HF)")
    ap.add_argument("--adapter", default=None, help="adapter dir (PEFT). If None, eval base only.")
    ap.add_argument("--eval-split", default="/home/ryu/projects/hinomoto-bench-ja/data/bench_v06_sft_eval.jsonl")
    ap.add_argument("--per-axis", type=int, default=2, help="items per axis to eval")
    ap.add_argument("--out", default="cultural_sft_eval_smoke.jsonl")
    ap.add_argument("--max-new", type=int, default=100)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s [%(levelname)s] %(message)s")

    eval_data = load_eval(Path(args.eval_split))
    logger.info("eval split: %d axes, total %d items",
                len(eval_data), sum(len(v) for v in eval_data.values()))

    # Tokenizer (always from base)
    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token

    # Load base
    logger.info("loading base: %s", args.base)
    model = AutoModelForCausalLM.from_pretrained(
        args.base, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True,
    )
    model.eval()

    # Optionally apply adapter
    if args.adapter:
        logger.info("attaching adapter: %s", args.adapter)
        model = PeftModel.from_pretrained(model, args.adapter)
        model = model.merge_and_unload() if hasattr(model, 'merge_and_unload') else model
        model.eval()

    # Generate
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_total = 0
    with out_path.open("w", encoding="utf-8") as fw:
        for axis in sorted(eval_data.keys()):
            items = eval_data[axis][:args.per_axis]
            print(f"\n=== axis: {axis} ({len(items)} items) ===")
            for it in items:
                prompt = it["prompt"]
                gold = it["response"]
                gen = generate(model, tok, prompt, max_new=args.max_new)
                fw.write(json.dumps({
                    "id": it.get("id"),
                    "axis": axis,
                    "prompt": prompt,
                    "gold": gold,
                    "generated": gen,
                }, ensure_ascii=False) + "\n")
                fw.flush()
                n_total += 1
                # Print compact
                print(f"  [{it.get('id'):20}]")
                print(f"    prompt: ...{prompt[-80:]}")
                print(f"    gold  : {gold[:80]}")
                print(f"    gen   : {gen[:80]}")
    logger.info("wrote %d items to %s", n_total, out_path)


if __name__ == "__main__":
    main()
