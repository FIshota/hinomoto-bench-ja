"""Compare base 3B vs base+SFT adapter on the same eval items.

Reads:
  /home/ryu/3day_logs/cultural_sft_eval_BASE.jsonl       — base only
  /home/ryu/3day_logs/cultural_sft_eval_extended.jsonl   — base + SFT adapter

Both should have same 40 items (8 axes × 5).
Compares:
- response length distribution
- gold-overlap (rough character overlap)
- artifact rate (HTML tags, English fragments, placeholder)
- per-axis breakdown
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_PATH = Path("/home/ryu/3day_logs/cultural_sft_eval_BASE.jsonl")
SFT_PATH = Path("/home/ryu/3day_logs/cultural_sft_eval_extended.jsonl")


def load_eval(p: Path) -> dict[str, dict]:
    """id → item"""
    out = {}
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                it = json.loads(line)
                out[it["id"]] = it
    return out


def clean_gen(gen: str) -> str:
    """Strip chat-template tokens."""
    gen = gen.replace("<|assistant|>", "").replace("<|endoftext|>", "")
    gen = gen.replace("<|user|>", "").replace("<|system|>", "")
    return gen.strip()


def char_overlap(a: str, b: str) -> float:
    """Rough char-bigram overlap (0..1)."""
    if not a or not b:
        return 0.0
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))
    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / max(1, min(len(ba), len(bb)))


# Artifact detectors
ENGLISH_RUN = re.compile(r"[a-zA-Z]{4,}")
BACKTICK = re.compile(r"`[^`]*`")
HTML_TAG = re.compile(r"<\/?(em|p|br|span|div)>", re.IGNORECASE)
PLACEHOLDER = re.compile(r"^[\s\.\?…」、,「!！？]+$")


def artifact_score(gen: str) -> dict[str, int]:
    s = clean_gen(gen)
    return {
        "english_fragment": len(ENGLISH_RUN.findall(s)),
        "backtick": len(BACKTICK.findall(s)),
        "html_tag": len(HTML_TAG.findall(s)),
        "placeholder_only": 1 if PLACEHOLDER.match(s) else 0,
    }


def main():
    base = load_eval(BASE_PATH)
    sft = load_eval(SFT_PATH)
    common = sorted(set(base.keys()) & set(sft.keys()))
    print(f"loaded {len(base)} base, {len(sft)} sft, common = {len(common)}")
    if not common:
        print("ERROR: no common items"); return 1

    # Per-axis aggregation
    per_axis = defaultdict(lambda: {
        "base_lens": [], "sft_lens": [],
        "base_overlap": [], "sft_overlap": [],
        "base_artifacts": defaultdict(int),
        "sft_artifacts": defaultdict(int),
    })
    for iid in common:
        b = base[iid]; s = sft[iid]
        axis = b.get("axis", "?")
        gold = b.get("gold", "")
        b_gen = clean_gen(b.get("generated", ""))
        s_gen = clean_gen(s.get("generated", ""))
        per_axis[axis]["base_lens"].append(len(b_gen))
        per_axis[axis]["sft_lens"].append(len(s_gen))
        per_axis[axis]["base_overlap"].append(char_overlap(b_gen, gold))
        per_axis[axis]["sft_overlap"].append(char_overlap(s_gen, gold))
        for k, v in artifact_score(b_gen).items():
            per_axis[axis]["base_artifacts"][k] += v
        for k, v in artifact_score(s_gen).items():
            per_axis[axis]["sft_artifacts"][k] += v

    def avg(lst):
        return sum(lst) / max(1, len(lst))

    print()
    print(f"{'axis':<18} {'n':>3} {'len_base':>9} {'len_sft':>8} {'overlap_base':>13} {'overlap_sft':>12} {'art_base':>9} {'art_sft':>8}")
    print("-" * 90)
    grand = defaultdict(list)
    for axis in sorted(per_axis.keys()):
        d = per_axis[axis]
        lb, ls = avg(d["base_lens"]), avg(d["sft_lens"])
        ob, os_ = avg(d["base_overlap"]), avg(d["sft_overlap"])
        ab = sum(d["base_artifacts"].values())
        as_ = sum(d["sft_artifacts"].values())
        n = len(d["base_lens"])
        grand["lb"].append(lb); grand["ls"].append(ls)
        grand["ob"].append(ob); grand["os_"].append(os_)
        grand["ab"].append(ab); grand["as_"].append(as_)
        print(f"{axis:<18} {n:>3} {lb:>9.1f} {ls:>8.1f} {ob:>13.3f} {os_:>12.3f} {ab:>9} {as_:>8}")
    print("-" * 90)
    print(f"{'GRAND':<18} {'':>3} {avg(grand['lb']):>9.1f} {avg(grand['ls']):>8.1f} "
          f"{avg(grand['ob']):>13.3f} {avg(grand['os_']):>12.3f} "
          f"{sum(grand['ab']):>9} {sum(grand['as_']):>8}")

    # Net SFT effect
    print()
    overlap_lift = avg(grand['os_']) - avg(grand['ob'])
    overlap_lift_pct = overlap_lift / max(0.0001, avg(grand['ob'])) * 100
    art_delta = sum(grand['as_']) - sum(grand['ab'])
    print(f"SFT net effect:")
    print(f"  gold-overlap lift: +{overlap_lift:.3f} ({overlap_lift_pct:+.1f}%)")
    print(f"  artifact delta: {art_delta:+d} ({'SFT better' if art_delta < 0 else 'BASE better' if art_delta > 0 else 'tie'})")
    print(f"  avg length delta: {avg(grand['ls']) - avg(grand['lb']):+.1f} chars")

    # Sample side-by-side
    print()
    print("=" * 90)
    print("Side-by-side samples (1 per axis)")
    print("=" * 90)
    shown = set()
    for iid in common:
        axis = base[iid].get("axis", "?")
        if axis in shown:
            continue
        shown.add(axis)
        b_gen = clean_gen(base[iid].get("generated", ""))
        s_gen = clean_gen(sft[iid].get("generated", ""))
        gold = base[iid].get("gold", "")
        print(f"\n--- {axis} [{iid}] ---")
        print(f"  gold:  {gold[:80]}")
        print(f"  BASE:  {b_gen[:80]}")
        print(f"  SFT:   {s_gen[:80]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
