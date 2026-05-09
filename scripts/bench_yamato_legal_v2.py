"""Yamato bench v2 — direct llama-cpp-python (in-process, no server lifecycle).

Bypasses HTTP server issues (WSL session SIGHUP). Loads model directly into Python.

Requires: `pip install llama-cpp-python` (CUDA build recommended for speed).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

BENCH = Path('/home/ryu/projects/hinomoto-bench-ja/data/yamato_legal.jsonl')
YAMATO_Q4 = '/mnt/d/hinomoto-data/artifacts/yamato_3b_v2_merged_hf/yamato_3b_v2.Q4_K_M.gguf'
SFT_V4_DPO_Q4 = '/mnt/d/hinomoto-data/artifacts/sft_v4_dpo_merged_hf/sft_v4_dpo.Q4_K_M.gguf'
OUT = Path('/home/ryu/projects/hinomoto-bench-ja/results/yamato_legal_bench_v2.json')

SYS = "あなたは日本の法律に詳しいアシスタントです。出典付きで回答し、最後に弁護士相談の注意書きを添えてください。"


def eval_model(gguf_path: str, items: list, n_ctx: int = 2048) -> list:
    """Load model in-process, eval all items, free."""
    from llama_cpp import Llama
    print(f'\n[loading {gguf_path.split("/")[-1]}]')
    llm = Llama(model_path=gguf_path, n_ctx=n_ctx, n_gpu_layers=99, verbose=False)
    print('  loaded')

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
        print(f"  {item['id']}: {len(resp)}c — {resp[:60].strip()}")
    del llm
    return results


def score(results, items):
    item_map = {it['id']: it for it in items}
    detail = []
    total_kw = 0
    total_kw_max = 0
    anti_hits = 0
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
        detail.append({
            'id': r['id'], 'category': item['category'],
            'kw': f'{kw_hit}/{len(kws)}', 'anti': anti_hit, 'len': len(resp),
        })
    return {
        'kw_total': f'{total_kw}/{total_kw_max} ({total_kw/max(1,total_kw_max)*100:.1f}%)',
        'anti_total': anti_hits, 'detail': detail,
    }


def main():
    items = [json.loads(l) for l in BENCH.read_text(encoding='utf-8').splitlines() if l.strip()]
    print(f'bench items: {len(items)}')

    out = {}

    if Path(YAMATO_Q4).exists():
        results = eval_model(YAMATO_Q4, items)
        out['yamato_3b_v2_q4'] = {
            'score': score(results, items),
            'samples': [{**r, **next(it for it in items if it['id'] == r['id'])} for r in results[:3]],
        }
    else:
        print(f'!! missing {YAMATO_Q4}')

    if Path(SFT_V4_DPO_Q4).exists():
        results = eval_model(SFT_V4_DPO_Q4, items)
        out['hinomoto_3b_sft_v4_dpo_q4'] = {
            'score': score(results, items),
            'samples': [{**r, **next(it for it in items if it['id'] == r['id'])} for r in results[:3]],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n✅ saved → {OUT}')

    print('\n=== Summary ===')
    for k, v in out.items():
        s = v['score']
        print(f'{k}: kw {s["kw_total"]}, anti {s["anti_total"]}')


if __name__ == '__main__':
    main()
