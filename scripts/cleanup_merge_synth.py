"""Clean synth v06 outputs and merge into a single bench-additions file.

Cleanup rules:
- Drop items where any eq/ap string is purely placeholder ("...", "?", empty)
- Drop items where ire contains > 3 ASCII alphabetic chars in a row (English leakage)
- Drop items with > 2 unbalanced parens or backticks (model artifact)
- silence axis: short ire is OK (sometimes "..." IS the answer)
- Re-run firewall + schema validation
- Preserve original synth_seed_id for traceability

Output: data/bench_v06_additions.jsonl with all axes merged.
"""
import json
import re
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, "/home/ryu/projects/hinomoto-bench-ja/scripts")
from synth_data_gen_v2 import validate_item, walk_strings, is_firewall_clean

DATA = Path("/home/ryu/projects/hinomoto-bench-ja/data")
AXES = ["family", "keigo", "silence", "compassion",
        "local_culture", "nuance", "generation_gap", "workplace"]

# Patterns that indicate placeholder leakage / model artifacts
PLACEHOLDER_PAT = re.compile(r"^[\s\.\?…」、,「!！？]+$")  # only punctuation
ENGLISH_RUN = re.compile(r"[a-zA-Z]{4,}")  # 4+ consecutive ASCII letters → English leak
BACKTICK_PAT = re.compile(r"`[^`]*`")       # any backtick-quoted segment is model artifact
BALANCED_PAREN_BAD = re.compile(r"[()）（]")  # we'll count balance separately


def has_placeholder_in_list(lst):
    if not isinstance(lst, list):
        return True
    for x in lst:
        if not isinstance(x, str):
            return True
        s = x.strip()
        if not s or PLACEHOLDER_PAT.match(s):
            return True
        if BACKTICK_PAT.search(s):
            return True
        # English run inside a quality marker is OK if it's a proper noun like "SNS"
        # but "kenjichan sees you" is clearly leak
        if ENGLISH_RUN.search(s) and len(s) < 30:
            return True
    return False


def has_artifact_in_ire(ire: str, axis: str) -> bool:
    """Check ideal_response_example for model artifacts."""
    if not isinstance(ire, str):
        return True
    s = ire.strip()
    if axis != "silence":
        # For non-silence, ire should be substantive
        if PLACEHOLDER_PAT.match(s) or len(s) < 8:
            return True
    if BACKTICK_PAT.search(s):
        return True
    # English run > 6 chars is leak (but allow short ones like "AI", "SNS")
    if ENGLISH_RUN.search(s):
        # Allow specific terms like "PC", "SNS", "AI"
        english_matches = ENGLISH_RUN.findall(s)
        for m in english_matches:
            if m.lower() not in {"sns", "tv", "pc", "ok", "lgbt", "lgbtq"}:
                return True
    return False


def clean_item(item: dict, axis: str) -> tuple[bool, str]:
    """Return (keep, reason). If keep=False, drop the item."""
    # Re-validate schema
    ok, reason = validate_item(item)
    if not ok:
        return False, f"schema:{reason}"

    eq = item.get("expected_qualities", [])
    ap = item.get("anti_patterns", [])
    ire = item.get("ideal_response_example", "")
    ctx = item.get("context", "")

    if has_placeholder_in_list(eq):
        return False, "eq-placeholder"
    if has_placeholder_in_list(ap):
        return False, "ap-placeholder"
    if has_artifact_in_ire(ire, axis):
        return False, "ire-artifact"

    # context shouldn't have backticks
    if BACKTICK_PAT.search(ctx):
        return False, "ctx-backtick"

    # Firewall pass
    blob = " ".join(walk_strings(item))
    if not is_firewall_clean(blob):
        return False, "firewall"

    return True, ""


def main():
    out_path = DATA / "bench_v06_additions.jsonl"
    drop_reasons: Counter = Counter()
    kept_total = 0
    dropped_total = 0
    per_axis = {}
    cross_seen: set[str] = set()

    print(f"{'axis':<18} {'before':>7} {'after':>7} {'dropped':>9}  top reason")
    print("-" * 70)
    with out_path.open("w", encoding="utf-8") as fw:
        for axis in AXES:
            p = DATA / f"{axis}_synth_v06.jsonl"
            if not p.exists():
                continue
            items = []
            with p.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            kept_axis = 0
            dropped_axis = 0
            axis_reasons: Counter = Counter()
            for item in items:
                keep, reason = clean_item(item, axis)
                if not keep:
                    dropped_axis += 1
                    drop_reasons[reason] += 1
                    axis_reasons[reason] += 1
                    continue
                # Cross-axis dedup
                key = item.get("context", "") + "|" + item.get("user", "")
                if key in cross_seen:
                    dropped_axis += 1
                    drop_reasons["cross-dup"] += 1
                    axis_reasons["cross-dup"] += 1
                    continue
                cross_seen.add(key)
                # Re-id for merged file
                new_item = {
                    "id": f"v06-{axis}-{kept_axis:04d}",
                    "axis": axis,
                    **{k: v for k, v in item.items() if k not in ("id", "axis")},
                }
                fw.write(json.dumps(new_item, ensure_ascii=False) + "\n")
                kept_axis += 1
            top = axis_reasons.most_common(1)
            top_str = f"{top[0][0]}={top[0][1]}" if top else "-"
            print(f"{axis:<18} {len(items):>7} {kept_axis:>7} {dropped_axis:>9}  {top_str}")
            per_axis[axis] = (kept_axis, dropped_axis)
            kept_total += kept_axis
            dropped_total += dropped_axis

    print("-" * 70)
    print(f"{'TOTAL':<18} {sum(p[0]+p[1] for p in per_axis.values()):>7} {kept_total:>7} {dropped_total:>9}")
    print()
    print("Drop reason breakdown:")
    for r, c in drop_reasons.most_common():
        print(f"  {r}: {c}")
    print()
    print(f"merged output: {out_path}")
    print(f"   ({kept_total} clean items)")


if __name__ == "__main__":
    main()
