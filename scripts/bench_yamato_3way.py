"""Yamato v1 vs v2 vs v3 (r=32) on Yamato-Bench-ja v0.2 (30 items).
Tests if increased LoRA rank captures more nuance on small-domain SFT.
"""
from __future__ import annotations
import json, gc
from pathlib import Path

BENCH = Path('/home/ryu/projects/hinomoto-bench-ja/data/yamato_legal_v02.jsonl')
TARGETS = [
    ('v1_r16',   '/mnt/d/hinomoto-data/artifacts/yamato_3b_v1_merged_hf/yamato_3b_v1.Q4_K_M.gguf'),
    ('v2_r16',   '/mnt/d/hinomoto-data/artifacts/yamato_3b_v2_merged_hf/yamato_3b_v2.Q4_K_M.gguf'),
    ('v3_r32',   '/mnt/d/hinomoto-data/artifacts/yamato_3b_v3_r32_merged_hf/yamato_3b_v3_r32.Q4_K_M.gguf'),
]
OUT = Path('/home/ryu/projects/hinomoto-bench-ja/results/yamato_3way_bench_v02.json')

SYS = "あなたは日本の法律に詳しいアシスタントです。出典付きで回答し、最後に弁護士相談の注意書きを添えてください。"


def eval_model(gguf_path, items):
    from llama_cpp import Llama
    print(f'\n[loading {gguf_path.split("/")[-1]}]')
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
    total_kw = total_kw_max = anti_hits = 0
    new_kw = new_kw_max = 0
    lens = []
    for r in results:
        item = item_map[r['id']]
        kws = item.get('expected_keywords', [])
        anti = item.get('anti_patterns', [])
        kw_hit = sum(1 for k in kws if k in r['response'])
        anti_hit = sum(1 for a in anti if a in r['response'])
        total_kw += kw_hit
        total_kw_max += len(kws)
        anti_hits += anti_hit
        lens.append(len(r['response']))
        idx = int(r['id'].split('_')[1])
        if idx >= 21:
            new_kw += kw_hit
            new_kw_max += len(kws)
    return {
        'overall': f'{total_kw}/{total_kw_max} ({total_kw/max(1,total_kw_max)*100:.1f}%)',
        'overall_pct': total_kw / max(1, total_kw_max) * 100,
        'new_domain': f'{new_kw}/{new_kw_max} ({new_kw/max(1,new_kw_max)*100:.1f}%)',
        'new_domain_pct': new_kw / max(1, new_kw_max) * 100,
        'anti': anti_hits,
        'avg_len': sum(lens) / max(1, len(lens)),
    }


def main():
    items = [json.loads(l) for l in BENCH.read_text(encoding='utf-8').splitlines() if l.strip()]
    print(f'bench items: {len(items)}')
    out = {}
    for name, path in TARGETS:
        if not Path(path).exists():
            print(f'!! missing {path}')
            continue
        results = eval_model(path, items)
        out[name] = score(results, items)
        print(f'  {name}: {out[name]}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nsaved → {OUT}')
    print('\n=== Summary ===')
    print(f'{"variant":12s} {"overall":>15s} {"new_domain":>15s} {"avg_len":>8s}')
    for k, v in out.items():
        print(f'{k:12s} {v["overall"]:>15s} {v["new_domain"]:>15s} {v["avg_len"]:>8.0f}')


if __name__ == '__main__':
    main()
