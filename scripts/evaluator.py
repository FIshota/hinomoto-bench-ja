#!/usr/bin/env python3
"""HinoMotoBench-ja v0.1 evaluator (rule-based + LLM-as-Judge ready)

Usage:
    # Generate model responses, then evaluate
    python evaluator.py --bench family.jsonl --responses model_responses.jsonl --out scores.json

    # With LLM judge (要 ANTHROPIC_API_KEY or OPENAI_API_KEY)
    python evaluator.py --bench family.jsonl --responses model_responses.jsonl \\
        --judge claude-3-5-sonnet --out scores.json
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# -----------------------------------------------------------------------------
# Keigo: rule-based scorer
# -----------------------------------------------------------------------------
KEIGO_MARKERS = {
    "sonkeigo": ["いらっしゃ", "ご覧", "おっしゃ", "なさ", "お~になる", "お加減", "いかが", "くださ", "お越し", "申し上げ", "拝聴"],
    "kenjougo": ["伺", "申し上げ", "申しま", "参り", "拝", "お送りいたし", "弊社", "存じ", "頂戴", "賜"],
    "teineigo": ["です", "ます", "でしょう"],
    "tameguchi": [],  # 敬語マーカーがないことを期待
}

ANTI_PATTERNS_TAMEGUCHI = ["ございます", "いらっしゃ", "申し上げ"]


def score_keigo(item: dict, response: str) -> dict:
    level = item["level_required"]
    expected_markers = item["evaluation"]["honorific_markers"]
    anti = item["evaluation"]["anti_patterns"]

    matched = [m for m in expected_markers if m in response]
    has_anti = any(_naive_anti_match(a, response) for a in anti)

    if level == "tameguchi":
        # タメ口は敬語マーカーがないことが正しい
        present_keigo = any(m in response for m in ANTI_PATTERNS_TAMEGUCHI)
        score = 0 if present_keigo else 1
        passed = not present_keigo
    else:
        score = len(matched) / max(len(expected_markers), 1)
        passed = score >= 0.5 and not has_anti

    return {
        "id": item["id"],
        "level_required": level,
        "matched_markers": matched,
        "has_anti_pattern": has_anti,
        "score": round(score, 3),
        "passed": passed,
    }


def _naive_anti_match(anti_str: str, response: str) -> bool:
    """anti_pattern は '「xxx」（解説）' 形式が多い。引用符内のみチェック。"""
    if "「" in anti_str and "」" in anti_str:
        inside = anti_str[anti_str.index("「")+1:anti_str.index("」")]
        return inside in response
    return False


# -----------------------------------------------------------------------------
# Silence: rule-based detection
# -----------------------------------------------------------------------------
SILENCE_TOKENS = ["<silence>", "(沈黙)", "(無言)"]


def score_silence(item: dict, response: str) -> dict:
    """沈黙が ideal_action の場合、応答が短いか silence token を含むかを判定。"""
    ideal = item["ideal_action"]
    is_silence = any(t in response for t in SILENCE_TOKENS) or len(response.strip()) < 10

    examples = item["ideal_response_examples"]
    matches_example = any(ex in response or response in ex for ex in examples)

    passed = is_silence or matches_example
    return {
        "id": item["id"],
        "is_silence_or_short": is_silence,
        "matches_example": matches_example,
        "response_len": len(response.strip()),
        "passed": passed,
    }


# -----------------------------------------------------------------------------
# Family: LLM-as-judge (or simple heuristic fallback)
# -----------------------------------------------------------------------------
JUDGE_PROMPT = """あなたは家族 AI の応答品質を評価する審査員です。

# 入力
- 文脈: {context}
- ユーザー発言: {user}
- AI 応答: {response}
- 評価基準:
{rubric}

# タスク
4 つの軸（empathy, appropriateness, naturalness, warmth）でそれぞれ 0-3 点で採点せよ。
0 = 完全に不適切, 1 = やや不足, 2 = 良好, 3 = 模範的

JSON で返す:
{{"empathy": <int>, "appropriateness": <int>, "naturalness": <int>, "warmth": <int>, "comment": "<short>"}}
"""


def score_family_with_judge(item: dict, response: str, judge: str) -> dict:
    """LLM-as-judge による family 採点。"""
    if judge.startswith("claude"):
        return _judge_anthropic(item, response, judge)
    elif judge.startswith("gpt"):
        return _judge_openai(item, response, judge)
    else:
        return _heuristic_family_score(item, response)


def _heuristic_family_score(item: dict, response: str) -> dict:
    """API なしのフォールバック。応答長と anti-pattern 不在で素朴に判定。"""
    anti = item.get("anti_patterns", [])
    has_anti = any(a.split("（")[0].replace("「","").replace("」","") in response for a in anti if "「" in a)
    length_ok = 5 <= len(response) <= 200
    return {
        "id": item["id"],
        "empathy": 2 if not has_anti and length_ok else 1,
        "appropriateness": 2 if not has_anti else 0,
        "naturalness": 2 if length_ok else 1,
        "warmth": 2 if not has_anti else 1,
        "total": 8 if not has_anti and length_ok else 4,
        "method": "heuristic",
    }


def _judge_anthropic(item: dict, response: str, model: str) -> dict:
    try:
        import anthropic
    except ImportError:
        print("[WARN] anthropic SDK not installed, falling back to heuristic")
        return _heuristic_family_score(item, response)

    client = anthropic.Anthropic()
    rubric = "\n".join(f"  - {k}: {v}" for k, v in item.get("rubric", {}).items())
    prompt = JUDGE_PROMPT.format(
        context=item["context"], user=item["user"],
        response=response, rubric=rubric,
    )
    msg = client.messages.create(
        model=model, max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    try:
        # extract JSON from response
        start = text.index("{")
        end = text.rindex("}") + 1
        score = json.loads(text[start:end])
        score["id"] = item["id"]
        score["total"] = score["empathy"] + score["appropriateness"] + score["naturalness"] + score["warmth"]
        score["method"] = f"judge:{model}"
        return score
    except Exception as e:
        print(f"[WARN] judge parse failed for {item['id']}: {e}")
        return _heuristic_family_score(item, response)


def _judge_openai(item: dict, response: str, model: str) -> dict:
    """OpenAI judge (similar structure)."""
    try:
        import openai
    except ImportError:
        return _heuristic_family_score(item, response)
    # 略 — 必要時に実装
    return _heuristic_family_score(item, response)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bench", required=True, type=Path, help="bench JSONL path (family/keigo/silence)")
    p.add_argument("--responses", required=True, type=Path,
                   help="JSONL with {id, response}")
    p.add_argument("--judge", default=None, help="claude-3-5-sonnet-20241022 etc")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()

    bench = {item["id"]: item for item in load_jsonl(args.bench)}
    responses = {r["id"]: r["response"] for r in load_jsonl(args.responses)}

    results = []
    for item_id, item in bench.items():
        resp = responses.get(item_id, "")
        if not resp:
            print(f"[SKIP] no response for {item_id}")
            continue

        if args.bench.name.startswith("keigo"):
            results.append(score_keigo(item, resp))
        elif args.bench.name.startswith("silence"):
            results.append(score_silence(item, resp))
        elif args.bench.name.startswith("family"):
            if args.judge:
                results.append(score_family_with_judge(item, resp, args.judge))
            else:
                results.append(_heuristic_family_score(item, resp))

    # Summary
    if not results:
        print("[ERR] no results")
        return 1

    summary: dict[str, Any] = {"n": len(results)}
    if "passed" in results[0]:
        summary["pass_rate"] = sum(r["passed"] for r in results) / len(results)
    if "total" in results[0]:
        summary["mean_total"] = sum(r["total"] for r in results) / len(results)
        summary["max_possible"] = 12

    out = {"summary": summary, "results": results}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"[done] {len(results)} items scored → {args.out}")
    print(f"  summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
