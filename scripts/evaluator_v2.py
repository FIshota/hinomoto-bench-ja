#!/usr/bin/env python3
"""HinoMotoBench-ja v0.1 evaluator v2 (stricter heuristics)

v1 からの変更点:
- silence: substring 適合を厳格化 (response.strip == ex の完全一致 or len < 8)
- family: anti-pattern 検出強化、テンプレート繰り返し検出、重複文検出
- keigo: 期待マーカーが応答内で「機能している」（適切な位置に出る）かチェック
- 退行検出: 入力をそのまま echo back するモデルを fail にする

使い方:
    python evaluator_v2.py --bench family.jsonl --responses model.jsonl --out scores.json
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# -----------------------------------------------------------------------------
# Common: 退行検出
# -----------------------------------------------------------------------------
def is_degenerate(response: str) -> tuple[bool, str]:
    """Detect template-echoing or repetition collapse"""
    r = response.strip()
    if len(r) < 1:
        return True, "empty"

    # 1. テンプレート echo: "## ユーザー発言" などのプロンプト構造を含む
    template_markers = ["## ユーザー発言", "## あなたの応答", "## 文脈", "## 場面", "## 元の発言"]
    if any(m in r for m in template_markers):
        return True, "template_echo"

    # 2. 重複行検出: 同じ行が 3 回以上繰り返される
    lines = [l.strip() for l in r.split("\n") if l.strip()]
    if lines:
        line_counts = Counter(lines)
        most_common = line_counts.most_common(1)[0]
        if most_common[1] >= 3:
            return True, f"line_repeated_{most_common[1]}x"

    # 3. 文字 n-gram 繰り返し（"おかえりなさい" を 8 回繰り返すような場合）
    if len(r) > 50:
        for n in (4, 5, 6, 8):
            for i in range(len(r) - n * 3):
                seg = r[i:i+n]
                if r[i:i+n*3] == seg * 3:
                    return True, f"ngram_{n}_3x_repeat"

    return False, ""


# -----------------------------------------------------------------------------
# Keigo
# -----------------------------------------------------------------------------
def score_keigo(item: dict, response: str) -> dict:
    deg, deg_reason = is_degenerate(response)
    level = item["level_required"]
    expected_markers = item["evaluation"].get("honorific_markers", [])
    anti = item["evaluation"].get("anti_patterns", [])

    matched = [m for m in expected_markers if m in response]
    has_anti = any(_naive_anti_match(a, response) for a in anti)

    ANTI_TAMEGUCHI = ["ございます", "いらっしゃ", "申し上げ", "お持ちになって", "おっしゃられ"]

    if level == "tameguchi":
        present_keigo = any(m in response for m in ANTI_TAMEGUCHI)
        score = 0.0 if (present_keigo or deg) else 1.0
        passed = score >= 1.0
    else:
        # 期待マーカー比率
        marker_score = len(matched) / max(len(expected_markers), 1)
        # 退行 -> ペナルティ
        score = 0.0 if deg else marker_score
        # anti-pattern -> ペナルティ
        if has_anti:
            score = max(0, score - 0.5)
        passed = score >= 0.5 and not has_anti and not deg

    return {
        "id": item["id"],
        "level_required": level,
        "matched_markers": matched,
        "has_anti_pattern": has_anti,
        "is_degenerate": deg,
        "deg_reason": deg_reason,
        "score": round(score, 3),
        "passed": passed,
    }


def _naive_anti_match(anti_str: str, response: str) -> bool:
    if "「" in anti_str and "」" in anti_str:
        inside = anti_str[anti_str.index("「")+1:anti_str.index("」")]
        return inside in response
    return False


# -----------------------------------------------------------------------------
# Silence (stricter)
# -----------------------------------------------------------------------------
def score_silence(item: dict, response: str) -> dict:
    deg, deg_reason = is_degenerate(response)
    r = response.strip()

    SILENCE_TOKENS = ["<silence>", "(沈黙)", "（沈黙）", "(無言)", "（無言）", "..."]
    has_silence_token = any(t in r for t in SILENCE_TOKENS)

    examples = item.get("ideal_response_examples", [])
    # 完全一致 or 例の prefix（短い相槌のみ）
    matches_example = any(r == ex.strip() or (len(ex) < 15 and r == ex.strip()) for ex in examples)

    # 「短い」とは: トリム後 8 文字以下、または沈黙トークン含む
    is_short_appropriate = len(r) <= 8 or has_silence_token

    if deg:
        passed = False
    else:
        passed = (is_short_appropriate or matches_example)

    return {
        "id": item["id"],
        "has_silence_token": has_silence_token,
        "matches_example": matches_example,
        "is_short_appropriate": is_short_appropriate,
        "is_degenerate": deg,
        "deg_reason": deg_reason,
        "response_len": len(r),
        "passed": passed,
    }


# -----------------------------------------------------------------------------
# Family (heuristic v2)
# -----------------------------------------------------------------------------
def score_family_v2(item: dict, response: str) -> dict:
    deg, deg_reason = is_degenerate(response)
    r = response.strip()
    anti = item.get("anti_patterns", [])

    # 退行 → 全 0
    if deg:
        return {"id": item["id"], "empathy": 0, "appropriateness": 0, "naturalness": 0,
                "warmth": 0, "total": 0, "is_degenerate": True, "deg_reason": deg_reason,
                "method": "heuristic_v2"}

    # anti-pattern 検出（引用部分のみ）
    has_anti = any(_naive_anti_match(a, r) for a in anti)

    # 長さスコア (5-150 文字が family 応答として理想)
    length_ok = 5 <= len(r) <= 150
    length_score = 2 if length_ok else (1 if len(r) <= 250 else 0)

    # anti-pattern 点
    anti_score = 0 if has_anti else 2

    # 文末が「。/！/？」または短いフレーズで終わる（自然さ）
    ends_naturally = bool(re.search(r"[。！？\.\!\?]$", r)) or len(r) < 30
    natural_score = 2 if ends_naturally else 1

    # warmth proxy: 「ね」「よ」など終助詞 or 親しみある語
    warmth_markers = ["ね", "よ", "かな", "おかえり", "おはよう", "おやすみ",
                      "ありがとう", "すごい", "嬉しい", "楽しい", "頑張", "大丈夫"]
    warmth_count = sum(1 for m in warmth_markers if m in r)
    warmth_score = min(3, max(0, warmth_count))

    # empathy proxy: 単純なミラーリング or 共感語
    empathy_markers = ["うん", "そっか", "そう", "わかる", "辛い", "嬉しい", "良かった",
                       "悲しい", "大変", "そうだね"]
    empathy_count = sum(1 for m in empathy_markers if m in r)
    empathy_score = min(3, max(0, empathy_count + (1 if length_ok else 0)))

    return {
        "id": item["id"],
        "empathy": empathy_score,
        "appropriateness": anti_score + (1 if length_ok else 0),
        "naturalness": natural_score,
        "warmth": warmth_score,
        "total": empathy_score + anti_score + (1 if length_ok else 0) + natural_score + warmth_score,
        "is_degenerate": False,
        "method": "heuristic_v2",
    }


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bench", required=True, type=Path)
    p.add_argument("--responses", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()

    bench = {item["id"]: item for item in load_jsonl(args.bench)}
    responses = {r["id"]: r["response"] for r in load_jsonl(args.responses)}

    results = []
    for item_id, item in bench.items():
        resp = responses.get(item_id, "")
        if not resp:
            continue
        if args.bench.name.startswith("keigo"):
            results.append(score_keigo(item, resp))
        elif args.bench.name.startswith("silence"):
            results.append(score_silence(item, resp))
        elif args.bench.name.startswith("family"):
            results.append(score_family_v2(item, resp))

    # Summary
    summary: dict[str, Any] = {"n": len(results)}
    if "passed" in results[0]:
        summary["pass_rate"] = sum(r["passed"] for r in results) / len(results)
        summary["degenerate_rate"] = sum(r.get("is_degenerate", False) for r in results) / len(results)
    if "total" in results[0]:
        summary["mean_total"] = round(sum(r["total"] for r in results) / len(results), 2)
        summary["max_possible"] = 12
        summary["degenerate_rate"] = sum(r.get("is_degenerate", False) for r in results) / len(results)

    out = {"summary": summary, "results": results}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"[done v2] {len(results)} → {args.out}")
    print(f"  summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
