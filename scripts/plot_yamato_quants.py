"""Generate Yamato Q3-Q6 quant comparison figure for paper."""
import json
from pathlib import Path
import matplotlib.pyplot as plt

RESULTS = Path('/home/ryu/projects/hinomoto-bench-ja/results/yamato_all_quants_bench.json')
OUT = Path('/mnt/c/Users/ryu/Desktop/HinoMoto/paper_drafts/figs/fig7_yamato_quants.png')

d = json.load(open(RESULTS))
labels = ['Q3_K_M', 'Q4_K_M', 'Q5_K_M', 'Q6_K']
sizes_gb = [1.6, 2.0, 2.3, 2.6]
kw_pcts = [d[l]['kw_pct'] for l in labels]

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(labels, kw_pcts, color=['#ff6b6b', '#feca57', '#1dd1a1', '#48dbfb'])
for i, (bar, kw, sz) in enumerate(zip(bars, kw_pcts, sizes_gb)):
    ax.text(bar.get_x() + bar.get_width()/2, kw + 1.5,
            f'{kw:.1f}%\n({sz} GB)', ha='center', fontsize=11)

ax.set_ylabel('Keyword coverage (%) on Yamato-Bench-ja v0.1 (n=20)', fontsize=11)
ax.set_xlabel('Quantization variant', fontsize=11)
ax.set_title('Yamato-3B-v1: legal task quantization is monotonic-ish\n(opposite to HinoMoto silence task non-monotonic)', fontsize=12)
ax.set_ylim(0, 65)
ax.grid(axis='y', alpha=0.3)

OUT.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout()
plt.savefig(OUT, dpi=300, bbox_inches='tight')
print(f'saved {OUT}')
