"""Bench Yamato-3B-v2 on Yamato-Bench-ja v0.2 (30 items, expanded).
Compares v1 vs v2 to track domain expertise improvement.
"""
from __future__ import annotations
import json, gc
from pathlib import Path

BENCH = Path('/home/ryu/projects/hinomoto-bench-ja/data/yamato_legal_v02.jsonl')
ART = Path('/mnt/d/hinomoto-data/artifacts')
OUT = Path('/home/ryu/projects/hinomoto-bench-ja/results/yamato_v02_bench_v1_vs_v2.json')

MODELS = [
    ('yamato_3b_v1_q4', ART / 'yamato_3b_v1_merged_hf' / 'yamato_3b_v1.Q4_K_M.gguf'),
    ('yamato_3b_v2_q4', ART / 'yamato_3b_v2_merged_hf' / 'yamato_3b_v2.Q4_K_M.gguf'),
]
SYS = "あなたは日本の法律に詳しいアシスタントです。出典付きで回答し、最後に弁護士相談の注意書きを添えてください。"


def eval_model(gguf_path: str, items: list) -> list:
    from llama_cpp import Llama
    llm = Llama(model_path=gguf_path, n_ctx=2048, n_gpu_layers=99, verbose=False)
    results = []
    for item in items:
        try:
            out = llm.create_chat_completion(
                messages=[
                    {'role': 'system', 'content': SYS},
                    {'role': 'user', 'content': item['user']},
                ],
                max_tokens=350, temperature=0.3, top_p=0.9,
                repeat_penalty=1.18,
            )
            resp = out['choices'][0]['message']['content']
        except Exception as e:
            resp = f'ERR: {e}'
        results.append({'id': item['id'], 'response': resp})
    del llm
    gc.collect()
    return results


def score(results, items):
    item_map = {it['id']: it for it in items}
    total_kw = 0; total_kw_max = 0; anti_hits = 0; lens = []
    for r in results:
        item = item_map[r['id']]
        resp = r['response']
        kws = item.get('expected_keywords', [])
        anti = item.get('anti_patterns', [])
        kw_hit = sum(1 for k in kws if k in resp)
        anti_hit = sum(1 for a in anti if a in resp)
        total_kw += kw_hit
        total_kw_max += len(kws)
        anti_hits += anti_hit
        lens.append(len(resp))
    return {
        'kw_total': f'{total_kw}/{total_kw_max} ({total_kw/max(1,total_kw_max)*100:.1f}%)',
        'kw_pct': total_kw / max(1, total_kw_max) * 100,
        'anti_total': anti_hits,
        'avg_len': sum(lens) / max(1, len(lens)),
    }


def main():
    items = [json.loads(l) for l in BENCH.read_text(encoding='utf-8').splitlines() if l.strip()]
    print(f'bench items: {len(items)} (v0.2)')
    out = {}
    for name, path in MODELS:
        if not path.exists():
            print(f'!! missing {path}'); continue
        print(f'\n=== {name} ===')
        results = eval_model(str(path), items)
        s = score(results, items)
        print(f'  {name}: {s["kw_total"]}, anti {s["anti_total"]}, avg_len {s["avg_len"]:.0f}c')
        out[name] = s

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n=== Summary ===')
    for k, v in out.items():
        print(f'  {k}: {v["kw_total"]}, anti {v["anti_total"]}')


if __name__ == '__main__':
    main()
