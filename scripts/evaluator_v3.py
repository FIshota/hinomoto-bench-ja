"""HinoMoto-Bench-ja v0.3 evaluator with LLM-as-Judge support.

Adds:
- atmosphere axis (60 items, rubric 0-12)
- LLM-as-Judge mode for family/atmosphere (prompts judge with rubric → score)
- Local judge: HinoMoto-3B sft_v4 (no API key needed)
- API judge: GPT-4 / Claude (optional, env keys)

usage:
    python scripts/evaluator_v3.py --bench data/atmosphere.jsonl \\
        --responses my_model/atmosphere_responses.jsonl \\
        --out my_model/atmosphere_scores_v3.json \\
        --judge local --judge-model http://127.0.0.1:8092/completion
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from typing import Optional


def parse_score_block(text: str) -> Optional[int]:
    """Extract integer 0-12 from judge response."""
    m = re.search(r'(?:総合|score|合計|total)[:\s]*(\d+)', text, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        return max(0, min(12, v))
    # fallback: any digit 0-12
    m = re.search(r'\b(1[0-2]|\d)\b', text)
    if m:
        return int(m.group(1))
    return None


def judge_local(prompt_url: str, system: str, prompt: str,
                n_predict: int = 200) -> str:
    import requests
    full = f'<|system|>{system}<|user|>{prompt}<|assistant|>'
    r = requests.post(prompt_url, json={
        'prompt': full, 'n_predict': n_predict,
        'temperature': 0.3, 'top_p': 0.9,
    }, timeout=120)
    return r.json().get('content', '')


JUDGE_SYS_ATM = """あなたは家族会話の評価者です。
与えられた状況・ユーザー発言・モデルの応答を読み、以下 4 軸で 0-3 点ずつ採点してください。
- 雰囲気適合 (0-3): 場の雰囲気/空気を読めているか
- 自然さ (0-3): 不自然な表現や違和感はないか
- 適切な短さ (0-3): 場に応じた適切な長さか
- 期待値達成 (0-3): expected_atmosphere に沿っているか

出力形式:
理由: <短く>
雰囲気適合: <0-3>
自然さ: <0-3>
適切な短さ: <0-3>
期待値達成: <0-3>
総合: <0-12 の合計>
"""


def score_atmosphere_with_judge(items: list, responses: dict, judge_url: str) -> dict:
    """LLM-as-Judge で atmosphere を rubric scoring."""
    results = []
    correct = 0
    n_judged = 0
    total_score = 0
    for item in items:
        rid = item.get('id')
        resp = responses.get(rid)
        if resp is None:
            results.append({'id': rid, 'error': 'no response'})
            continue
        prompt = (
            f"## 状況\n{item.get('context','')}\n\n"
            f"## ユーザー発言\n{item.get('user','')}\n\n"
            f"## 期待される雰囲気\n{item.get('expected_atmosphere','')}\n\n"
            f"## アンチパターン (これに該当すると減点)\n" + ', '.join(item.get('anti_patterns', [])) + "\n\n"
            f"## モデルの応答\n{resp}\n\n"
            f"上記応答を採点してください。"
        )
        try:
            text = judge_local(judge_url, JUDGE_SYS_ATM, prompt)
        except Exception as e:
            text = f'ERROR: {e}'
        score = parse_score_block(text)
        if score is not None:
            total_score += score
            n_judged += 1
        results.append({'id': rid, 'response': resp, 'judge_text': text[:300], 'score': score})
    return {
        'n': len(items),
        'n_judged': n_judged,
        'mean_total': total_score / max(1, n_judged),
        'max_possible': 12,
        'degenerate_rate': sum(1 for r in results if r.get('response') and len(r['response']) < 3) / max(1, len(items)),
        'details': results,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bench', required=True)
    p.add_argument('--responses', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--judge', choices=['local', 'rule', 'gpt4', 'claude'], default='rule')
    p.add_argument('--judge-url', default='http://127.0.0.1:8092/completion',
                   help='for --judge=local')
    args = p.parse_args()

    items = [json.loads(l) for l in Path(args.bench).read_text(encoding='utf-8').splitlines() if l.strip()]
    responses = {}
    for line in Path(args.responses).read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        responses[d['id']] = d.get('response', '')

    bench_name = Path(args.bench).stem
    print(f'bench: {bench_name} ({len(items)} items)')
    print(f'responses: {len(responses)}')
    print(f'judge: {args.judge}')

    if bench_name == 'atmosphere' and args.judge == 'local':
        summary = score_atmosphere_with_judge(items, responses, args.judge_url)
    else:
        # Rule-based fallback (basic anti_pattern + length check)
        results = []
        passed = 0
        for item in items:
            rid = item['id']
            resp = responses.get(rid, '')
            anti = item.get('anti_patterns', [])
            ok = not any(ap in resp for ap in anti) and 0 < len(resp) < 200
            if ok: passed += 1
            results.append({'id': rid, 'response': resp[:200], 'pass': ok})
        summary = {
            'n': len(items), 'pass_rate': passed / max(1, len(items)),
            'degenerate_rate': sum(1 for r in results if not r['response']) / max(1, len(items)),
            'details': results,
        }

    out = {'bench': bench_name, 'judge': args.judge, 'summary': summary}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  summary: {{"n": {summary["n"]}, ...}}')
    print(f'✅ saved: {args.out}')


if __name__ == '__main__':
    main()
