"""Audit all synth_v06 outputs: firewall, schema, dedup, quality stats."""
import json
import sys
import re
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/ryu/projects/hinomoto-bench-ja/scripts")
from synth_data_gen_v2 import (
    is_firewall_clean, validate_item, walk_strings,
)

# Reuse the public_firewall regex for broader leak check
try:
    sys.path.insert(0, "/home/ryu/projects/ai-chan")
    from core.public_firewall import (
        _build_regex, DEFAULT_FORBIDDEN_TERMS, INTERNAL_FAMILY_SYSTEM_PROMPT_PATTERNS,
    )
    BROAD_FIREWALL = _build_regex(DEFAULT_FORBIDDEN_TERMS + INTERNAL_FAMILY_SYSTEM_PROMPT_PATTERNS)
    HAVE_BROAD_FIREWALL = True
except Exception as e:
    print(f"WARN: could not load public_firewall: {e}", file=sys.stderr)
    HAVE_BROAD_FIREWALL = False

AXES = ["family", "keigo", "silence", "compassion",
        "local_culture", "nuance", "generation_gap", "workplace"]
DATA = Path("/home/ryu/projects/hinomoto-bench-ja/data")


def load_jsonl(p: Path) -> list[dict]:
    items = []
    if not p.exists():
        return items
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ⚠ bad JSON line in {p.name}: {e}")
    return items


def main():
    total = 0
    grand_seen: set[str] = set()
    cross_dedup = 0
    grand_firewall_hits = 0
    grand_schema_fails = 0
    grand_quality_warnings = 0
    all_reasons: Counter = Counter()

    print(f"{'axis':<18} {'count':>6} {'valid':>6} {'firewall_hit':>13} {'cross_dup':>10} {'short_ire':>10} {'long_ire':>9}")
    print("-" * 90)

    for axis in AXES:
        p = DATA / f"{axis}_synth_v06.jsonl"
        items = load_jsonl(p)
        n = len(items)
        total += n
        valid = 0
        fw_hits = 0
        local_dups = 0
        short_ire = 0
        long_ire = 0
        for it in items:
            # Cross-axis dedup
            key = it.get("context", "") + "|" + it.get("user", "")
            if key in grand_seen:
                cross_dedup += 1
                local_dups += 1
            else:
                grand_seen.add(key)

            # Schema validate
            ok, reason = validate_item(it)
            if ok:
                valid += 1
            else:
                grand_schema_fails += 1
                all_reasons[reason] += 1

            # Broader firewall (cross-leak detection)
            if HAVE_BROAD_FIREWALL:
                blob = " ".join(walk_strings(it))
                if BROAD_FIREWALL.search(blob):
                    fw_hits += 1
                    grand_firewall_hits += 1

            # Quality heuristics: ideal_response_example length distribution
            ire = it.get("ideal_response_example", "")
            if isinstance(ire, str):
                if len(ire) < 10:
                    short_ire += 1
                if len(ire) > 280:
                    long_ire += 1

        print(f"{axis:<18} {n:>6} {valid:>6} {fw_hits:>13} {local_dups:>10} {short_ire:>10} {long_ire:>9}")

    print("-" * 90)
    print(f"{'TOTAL':<18} {total:>6}")
    print()
    print(f"Cross-axis dedup hits: {cross_dedup}")
    print(f"Schema-invalid items (re-validate): {grand_schema_fails}")
    print(f"Broad-firewall hits (ai-chan/Ai leak): {grand_firewall_hits}")
    if all_reasons:
        print()
        print("Top schema fail reasons:")
        for r, c in all_reasons.most_common(8):
            print(f"  {r}: {c}")

    # Sample audit: pick 3 random items per axis for visual review
    print()
    print("=" * 90)
    print("VISUAL SAMPLES (3 per axis)")
    print("=" * 90)
    import random
    random.seed(42)
    for axis in AXES:
        p = DATA / f"{axis}_synth_v06.jsonl"
        items = load_jsonl(p)
        if not items:
            continue
        print(f"\n--- {axis} ({len(items)} items) ---")
        for it in random.sample(items, min(3, len(items))):
            ctx = it.get("context", "")[:60]
            ire = it.get("ideal_response_example", "")[:80]
            eq = it.get("expected_qualities", [])
            ap = it.get("anti_patterns", [])
            print(f"  ctx: {ctx}")
            print(f"  ire: {ire}")
            print(f"  eq:  {eq[:3]}")
            print(f"  ap:  {ap[:3]}")
            print()


if __name__ == "__main__":
    main()
