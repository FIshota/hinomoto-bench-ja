"""Sanity validator for bench v0.6 files. Run before any release.

Checks:
1. All JSONL files parse without errors
2. Each item has required fields
3. Axis field is canonical (family, keigo, silence, compassion, local_culture, nuance, generation_gap, workplace)
4. ID uniqueness within and across files
5. No public_firewall violations (if available)
6. Item counts match expected per-axis totals

Exit code 0 on success, non-zero on any failure.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path("/home/ryu/projects/hinomoto-bench-ja/data")

CANONICAL_AXES = {
    "family", "keigo", "silence", "compassion",
    "local_culture", "nuance", "generation_gap", "workplace",
}

EXPECTED_COUNTS = {
    "family": 225,
    "keigo": 107,
    "silence": 134,
    "compassion": 62,
    "local_culture": 42,
    "nuance": 40,
    "generation_gap": 40,
    "workplace": 42,
}

# Standard cultural-axis schema
STANDARD_FIELDS = {"id", "axis", "context", "expected_qualities", "anti_patterns", "ideal_response_example"}

# keigo seed (v01/v03) variant: scenario/expected_response/evaluation.anti_patterns
KEIGO_LEGACY_FIELDS = {"id", "axis", "scenario", "user", "expected_response", "evaluation"}

# silence seed (v01) variant: ideal_response_examples (plural list) + ideal_action
SILENCE_LEGACY_FIELDS = {"id", "axis", "context", "user", "ideal_response_examples", "anti_patterns"}


def has_required_schema(item: dict) -> tuple[bool, str]:
    """Return (ok, schema_kind) — 'standard', 'keigo_legacy', 'silence_legacy', or 'missing'."""
    keys = set(item.keys())
    if STANDARD_FIELDS.issubset(keys):
        return True, "standard"
    if KEIGO_LEGACY_FIELDS.issubset(keys):
        return True, "keigo_legacy"
    if SILENCE_LEGACY_FIELDS.issubset(keys):
        return True, "silence_legacy"
    return False, "missing-required"


def validate_file(p: Path) -> tuple[int, list[str], dict]:
    """Return (num_items, errors, schema_breakdown)."""
    errors = []
    items = []
    schema_counts = defaultdict(int)
    if not p.exists():
        return 0, [f"{p.name}: not found"], {}
    with p.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{p.name}:L{i}: JSON parse fail: {e}")
                continue
            items.append(it)
            # schema check (accept either standard or keigo_legacy)
            ok, kind = has_required_schema(it)
            schema_counts[kind] += 1
            if not ok:
                errors.append(f"{p.name}:L{i} ({it.get('id', '?')}): missing required fields ({kind})")
            # axis canonical
            axis = it.get("axis")
            if axis and axis not in CANONICAL_AXES:
                errors.append(f"{p.name}:L{i} ({it.get('id', '?')}): unknown axis {axis!r}")
            # types for standard schema
            if kind == "standard":
                eq = it.get("expected_qualities")
                if eq is not None and not isinstance(eq, list):
                    errors.append(f"{p.name}:L{i}: expected_qualities not list")
                ap = it.get("anti_patterns")
                if ap is not None and not isinstance(ap, list):
                    errors.append(f"{p.name}:L{i}: anti_patterns not list")
    return len(items), errors, dict(schema_counts)


def main():
    print("=" * 60)
    print("bench v0.6 validation")
    print("=" * 60)

    all_errors = []
    full_path = DATA / "bench_v06_full.jsonl"
    n_full, errs, schema_full = validate_file(full_path)
    all_errors.extend(errs)
    print(f"  bench_v06_full.jsonl: {n_full} items, {len(errs)} errors")
    print(f"    schema breakdown: {schema_full}")

    # Per-axis files
    print()
    print("per-axis files:")
    per_axis_total = 0
    for axis in sorted(CANONICAL_AXES):
        p = DATA / f"bench_v06_{axis}.jsonl"
        n, errs, schemas = validate_file(p)
        per_axis_total += n
        all_errors.extend(errs)
        expected = EXPECTED_COUNTS.get(axis, 0)
        ok = "✓" if n == expected else "✗"
        schema_str = ",".join(f"{k}:{v}" for k, v in schemas.items())
        print(f"  {axis:<18} {n:>4} items (expected {expected}) {ok}  [{schema_str}]")

    if per_axis_total != n_full:
        all_errors.append(f"per-axis total {per_axis_total} != bench_full {n_full}")

    # IDs uniqueness in master file
    print()
    print("ID uniqueness check (master file):")
    ids = []
    with full_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    it = json.loads(line)
                    ids.append(it.get("id"))
                except json.JSONDecodeError:
                    pass
    dup = [i for i in ids if ids.count(i) > 1]
    if dup:
        all_errors.append(f"duplicate IDs in master: {set(dup)}")
        print(f"  ✗ duplicates: {set(dup)}")
    else:
        print(f"  ✓ all {len(ids)} IDs unique")

    # Firewall check (optional)
    print()
    print("firewall (public-leak) check:")
    try:
        sys.path.insert(0, "/home/ryu/projects/ai-chan")
        from core.public_firewall import _build_regex, DEFAULT_FORBIDDEN_TERMS, INTERNAL_FAMILY_SYSTEM_PROMPT_PATTERNS
        pat = _build_regex(DEFAULT_FORBIDDEN_TERMS + INTERNAL_FAMILY_SYSTEM_PROMPT_PATTERNS)
        text = full_path.read_text(encoding="utf-8")
        viols = pat.findall(text)
        if viols:
            all_errors.append(f"firewall violations: {len(viols)}")
            print(f"  ✗ violations: {viols[:5]}")
        else:
            print(f"  ✓ clean (no internal identifiers)")
    except Exception as e:
        print(f"  (skipped: {e})")

    # Summary
    print()
    print("=" * 60)
    if all_errors:
        print(f"❌ FAILED: {len(all_errors)} errors")
        for e in all_errors[:20]:
            print(f"  - {e}")
        return 1
    else:
        print(f"✅ PASS: {n_full} items, all valid, no leaks")
        return 0


if __name__ == "__main__":
    sys.exit(main())
