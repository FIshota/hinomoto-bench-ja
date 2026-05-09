"""Bench Yamato-3B-v1 vs Sarashina2.2-3B base on 20 legal Q&A items.

Compares:
- Yamato-3B-v1 (sft_v1 + 50 legal samples) — Q4_K_M GGUF
- Sarashina2.2-3B-instruct base — direct prompt (no GGUF cache)

Metric:
- expected_keywords coverage (% per response)
- anti_patterns avoidance (penalty when triggered)
"""
from __future__ import annotations
import json, sys, time, subprocess
from pathlib import Path

BENCH = Path('/home/ryu/projects/hinomoto-bench-ja/data/yamato_legal.jsonl')
LLAMA = '/home/ryu/projects/llama.cpp/build_cuda/bin/llama-server'
YAMATO = '/mnt/d/hinomoto-data/artifacts/yamato_3b_v1_merged_hf/yamato_3b_v1.Q4_K_M.gguf'
SARASHINA_BASE = '/mnt/d/hinomoto-data/artifacts/sft_v4_3b_merged_hf'  # closest available base

OUT = Path('/home/ryu/projects/hinomoto-bench-ja/results/yamato_legal_bench.json')


def run_llama_server_eval(gguf: str, items: list, port: int = 8094) -> list:
    """Spawn llama-server, eval all items, kill server."""
    import requests
    # log to file so we can debug
    log_path = f'/tmp/llama_bench_{port}.log'
    log_file = open(log_path, 'w')
    proc = subprocess.Popen([LLAMA, '-m', gguf, '--port', str(port),
                              '-c', '2048', '-ngl', '99'],
                              stdout=log_file, stderr=subprocess.STDOUT)
    print(f'  server PID={proc.pid}, log={log_path}')
    # poll /health until ready
    for _ in range(60):
        time.sleep(2)
        try:
            r = requests.get(f'http://127.0.0.1:{port}/health', timeout=3)
            if r.status_code == 200:
                print(f'  server ready on port {port}')
                break
        except Exception:
            pass
    try:
        results = []
        for item in items:
            sys_prompt = "あなたは日本の法律に詳しいアシスタントです。出典付きで回答し、最後に弁護士相談の注意書きを添えてください。"
            user = item['user']
            # Use OpenAI-compatible chat endpoint to leverage built-in chat template
            payload = {
                'messages': [
                    {'role': 'system', 'content': sys_prompt},
                    {'role': 'user', 'content': user},
                ],
                'max_tokens': 350, 'temperature': 0.3, 'top_p': 0.9,
            }
            try:
                r = requests.post(f'http://127.0.0.1:{port}/v1/chat/completions',
                                  json=payload, timeout=120)
                d = r.json()
                resp = d.get('choices', [{}])[0].get('message', {}).get('content', '')
                if not resp and 'error' in d:
                    resp = f'API_ERR: {d["error"]}'
            except Exception as e:
                resp = f'ERR: {e}'
            results.append({'id': item['id'], 'response': resp})
            print(f"  {item['id']}: {len(resp)} chars — {resp[:80]}")
        return results
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def score(results, items):
    """Score keyword coverage + anti-pattern avoidance."""
    item_map = {it['id']: it for it in items}
    detail = []
    total_kw = 0
    total_kw_max = 0
    anti_hits = 0
    for r in results:
        item = item_map[r['id']]
        resp = r['response']
        keywords = item.get('expected_keywords', [])
        anti = item.get('anti_patterns', [])
        kw_hit = sum(1 for k in keywords if k in resp)
        anti_hit = sum(1 for a in anti if a in resp)
        total_kw += kw_hit
        total_kw_max += len(keywords)
        anti_hits += anti_hit
        detail.append({
            'id': r['id'], 'category': item['category'],
            'kw_coverage': f'{kw_hit}/{len(keywords)}',
            'anti_hits': anti_hit, 'response_len': len(resp),
        })
    return {
        'kw_total': f'{total_kw}/{total_kw_max} ({total_kw/max(1,total_kw_max)*100:.1f}%)',
        'anti_total': anti_hits,
        'detail': detail,
    }


def main():
    items = [json.loads(l) for l in BENCH.read_text(encoding='utf-8').splitlines() if l.strip()]
    print(f'bench items: {len(items)}')

    out = {}

    # Yamato-3B-v1
    if Path(YAMATO).exists():
        print('\n=== Yamato-3B-v1 (Q4_K_M) ===')
        results = run_llama_server_eval(YAMATO, items, port=8094)
        out['yamato_3b_v1_q4'] = {'score': score(results, items),
                                   'samples': [{**r, **next(it for it in items if it['id'] == r['id'])} for r in results[:3]]}
        time.sleep(5)
    else:
        print(f'!! Yamato GGUF missing: {YAMATO}')

    # baseline (use sft_v4 as nearest available since Sarashina base is HF only)
    Q4_BASE = '/mnt/d/hinomoto-data/artifacts/sft_v4_dpo_merged_hf/sft_v4_dpo.Q4_K_M.gguf'
    if Path(Q4_BASE).exists():
        print('\n=== HinoMoto-3B sft_v4-DPO (Q4_K_M) — for comparison ===')
        results = run_llama_server_eval(Q4_BASE, items, port=8094)
        out['hinomoto_3b_sft_v4_dpo_q4'] = {'score': score(results, items),
                                             'samples': []}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n✅ saved → {OUT}')

    print('\n=== Summary ===')
    for k, v in out.items():
        print(f'{k}: kw {v["score"]["kw_total"]}, anti {v["score"]["anti_total"]}')


if __name__ == '__main__':
    main()
