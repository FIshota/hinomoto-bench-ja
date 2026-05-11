#!/usr/bin/env python3
"""Synthetic bench data generator — use HinoMoto-3B Q4 to expand HinoMoto-Bench-ja.

Strategy
--------
For each seed item in an existing bench file, prompt the local llama-server to
generate N similar (but distinct) items. The model is asked to follow the SAME
schema (id, axis, context, user, expected_qualities, anti_patterns, ideal_response_example)
but produce a NEW situation.

Outputs go through:
  1. JSON parse validation
  2. Public firewall (strip any internal-identifier leakage)
  3. Per-axis dedup (cosine similarity proxy via first-100-char hash)
  4. Quality filter (length, required fields, anti_patterns must be list)

Usage
-----
    # 10-item smoke test on family axis
    python synth_data_gen.py --bench data/family.jsonl \
        --output data/family_synth_v06.jsonl --n-per-seed 1 --max-output 10

    # full run for one axis (target ~1000 items)
    python synth_data_gen.py --bench data/family.jsonl \
        --output data/family_synth_v06.jsonl --n-per-seed 10 --max-output 1000

Pre-requisites
--------------
- llama-server running on http://127.0.0.1:8092 (verified via /health)
- The hinomoto-bench-ja seed file exists
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

LLAMA_BASE = "http://127.0.0.1:8092"
HEADERS = {"Content-Type": "application/json"}

logger = logging.getLogger("synth_gen")


# ── Firewall (re-import path-tolerant) ───────────────────────────────

FIREWALL_TERMS = (
    "ai-chan", "ai_chan", "AiChan", "AI-chan",
    "AIちゃん", "アイちゃん", "「ai-chan」", "「Ai」",
)
_FIREWALL_PAT = re.compile("|".join(re.escape(t) for t in FIREWALL_TERMS))


def is_firewall_clean(text: str) -> bool:
    return _FIREWALL_PAT.search(text or "") is None


# ── llama-server HTTP client ─────────────────────────────────────────


def llama_chat(prompt: str, *, n_predict: int = 1024, temperature: float = 0.85) -> Optional[str]:
    """Single-turn via OpenAI-compatible /v1/chat/completions (uses model chat template)."""
    payload = {
        "model": "ai_3b_v14.Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": "あなたは日本語 LLM 評価ベンチマーク作成の専門家です。指示に従い、JSON 配列のみを出力します。説明文や code block は出力しません。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": n_predict,
        "temperature": temperature,
        "top_p": 0.9,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{LLAMA_BASE}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("llama-server failed: %s", e)
        return None


# ── Prompt builder ──────────────────────────────────────────────────


AXIS_GUIDANCE = {
    "family": "家族 (親・配偶者・子・兄弟・祖父母) の場面に限定. 職場や友人の場面は禁止.",
    "keigo": "敬語 (尊敬・謙譲・丁寧) の使い分けが問われる場面. ビジネス / 公的場面.",
    "silence": "沈黙が正解の場面 (悲しみ・衝撃・尊厳・羞恥). 言葉を選ぶより黙る価値.",
    "compassion": "他者への思いやりが試される場面. 弱者支援・寄り添い・距離感.",
    "local_culture": "地方文化・慣習 (京都・東北・茶道・お中元・葬儀・冠婚葬祭).",
    "nuance": "日本語の言外の意味 (結構です・お疲れ様 vs ご苦労様・遠回しの断り).",
    "generation_gap": "祖父母↔孫 / 親↔若者 の世代差 (テクノロジー・価値観・距離感).",
    "workplace": "職場の場面 (上司部下・後輩指導・退職・ハラスメント・メンタル不調).",
}


def build_prompt(seed: dict, n_per_seed: int, axis: str = "family") -> str:
    """Construct a generation prompt from a seed item."""
    schema_keys = ["context", "user", "expected_qualities", "anti_patterns", "ideal_response_example"]
    seed_summary = {k: seed.get(k) for k in schema_keys if k in seed}
    axis_rule = AXIS_GUIDANCE.get(axis, "seed と同じ軸を厳守.")

    return (
        f"あなたは日本語 LLM 評価ベンチマーク作成の専門家. 軸: 「{axis}」.\n"
        f"軸の定義: {axis_rule}\n\n"
        "以下が seed (この軸に属する 1 例):\n"
        f"{json.dumps(seed_summary, ensure_ascii=False, indent=2)}\n\n"
        f"上記 seed と同じ軸・同じスキーマで、 別の場面の新しい項目を {n_per_seed} 個作成。\n"
        "厳守:\n"
        f"- 場面 (context) は seed と異なるが、 必ず軸「{axis}」内に収める\n"
        "- expected_qualities, anti_patterns はそれぞれ 2-4 個の文字列リスト\n"
        "- ideal_response_example は 5-300 字の自然な日本語\n"
        "- JSON 配列形式で出力 ([{...}, ...])。 説明文・コードブロック・前置きは禁止\n"
        "- 「ai-chan」「Ai」 等の固有モデル名は使用禁止\n"
        "\n出力:\n"
    )


# ── Validate + clean ─────────────────────────────────────────────────


# context, expected_qualities, anti_patterns, ideal_response_example are core.
# user is optional (some axes don't have a "ユーザー発言" turn).
REQUIRED_FIELDS = {"context", "expected_qualities", "anti_patterns", "ideal_response_example"}


def parse_response(text: str) -> list[dict]:
    """Try to extract a JSON array from the model output, with tolerant fix-ups."""
    text = text.replace("</s>", "")
    # Find the first [ ... ] block (greedy to capture all closing brackets)
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if not m:
        return []
    raw = m.group(0)

    # Try strict parse first
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        pass

    # Tolerant fix-ups for common LLM JSON errors
    fixed = raw
    fixed = re.sub(r'[「『]', '"', fixed)             # JP smart quotes opening
    fixed = re.sub(r'[」』]', '"', fixed)             # JP smart quotes closing
    fixed = re.sub(r"(?<=[:\[,\s])'", '"', fixed)    # opening single-quote → double
    fixed = re.sub(r"'(?=[,\]\s\}])", '"', fixed)    # closing single-quote → double
    fixed = re.sub(r',(\s*[\]\}])', r'\1', fixed)    # trailing commas

    try:
        items = json.loads(fixed)
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        return []


def _legacy_unused_parser(text: str) -> list[dict]:
    """Old parser kept for reference."""
    m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        return []


def validate_item(item: dict) -> bool:
    """Schema + sanity + firewall."""
    if not isinstance(item, dict):
        return False
    missing = REQUIRED_FIELDS - set(item.keys())
    if missing:
        return False
    # Field types
    if not isinstance(item.get("expected_qualities"), list):
        return False
    if not isinstance(item.get("anti_patterns"), list):
        return False
    if len(item.get("expected_qualities", [])) < 2:
        return False
    if len(item.get("anti_patterns", [])) < 2:
        return False
    # Length
    if len(item.get("ideal_response_example", "")) < 5:
        return False
    if len(item.get("ideal_response_example", "")) > 500:
        return False
    # Firewall — concatenate all string fields
    text_blob = " ".join(str(v) for v in item.values() if isinstance(v, (str,))) + \
                " ".join(str(x) for v in item.values() if isinstance(v, list) for x in v if isinstance(x, str))
    if not is_firewall_clean(text_blob):
        return False
    return True


def dedup_key(item: dict) -> str:
    """Cheap dedup hash from context + user (first 100 chars)."""
    return (str(item.get("context", "")) + "|" + str(item.get("user", "")))[:100]


# ── Main loop ────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, help="seed JSONL path")
    ap.add_argument("--output", required=True, help="output synth JSONL path")
    ap.add_argument("--n-per-seed", type=int, default=2, help="how many items per seed prompt")
    ap.add_argument("--max-output", type=int, default=100, help="max items to write")
    ap.add_argument("--axis", default="generated", help="axis label for new ids")
    ap.add_argument("--id-prefix", default="syn", help="id prefix")
    ap.add_argument("--temperature", type=float, default=0.85)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s [%(levelname)s] %(message)s")

    seeds_path = Path(args.bench)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seeds = []
    with seeds_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                seeds.append(json.loads(line))
    logger.info("loaded %d seeds from %s", len(seeds), seeds_path)

    seen_keys: set[str] = set()
    written = 0
    n_attempt = 0
    n_parse_fail = 0
    n_validate_fail = 0
    n_dedup = 0

    t0 = time.time()
    with out_path.open("w", encoding="utf-8") as fw:
        for seed_idx, seed in enumerate(seeds):
            if written >= args.max_output:
                break
            prompt = build_prompt(seed, args.n_per_seed, axis=args.axis)
            response = llama_chat(prompt, n_predict=1500, temperature=args.temperature)
            n_attempt += 1
            if response is None:
                continue

            items = parse_response(response)
            if not items:
                n_parse_fail += 1
                logger.debug("parse fail seed[%d]: %r", seed_idx, response[:200])
                continue

            for item in items:
                if not validate_item(item):
                    n_validate_fail += 1
                    continue
                k = dedup_key(item)
                if k in seen_keys:
                    n_dedup += 1
                    continue
                seen_keys.add(k)
                # Inject id + axis
                new_item = {
                    "id": f"{args.id_prefix}-{written:04d}",
                    "axis": args.axis,
                    **item,
                    "synth_seed_id": seed.get("id"),
                }
                fw.write(json.dumps(new_item, ensure_ascii=False) + "\n")
                fw.flush()  # ensure on-disk durability against SIGTERM
                written += 1
                if written >= args.max_output:
                    break

            if seed_idx % 10 == 0:
                elapsed = time.time() - t0
                rate = written / max(1, elapsed)
                logger.info(
                    "progress: %d seeds → %d written (parse_fail=%d validate_fail=%d dedup=%d) [%.1f items/s]",
                    seed_idx + 1, written, n_parse_fail, n_validate_fail, n_dedup, rate
                )

    logger.info(
        "done: %d items in %s (attempts=%d parse_fail=%d validate_fail=%d dedup=%d, %.0f sec)",
        written, out_path, n_attempt, n_parse_fail, n_validate_fail, n_dedup, time.time() - t0
    )
    return 0 if written > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
