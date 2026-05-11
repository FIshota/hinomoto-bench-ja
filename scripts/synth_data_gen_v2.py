#!/usr/bin/env python3
"""Synthetic bench data generator v2 — robust per-axis expansion.

Improvements over v1
--------------------
- Per-seed retry loop with temperature ramp (0.85 → 0.95 → 1.05)
- n_per_seed default 10 (was 2)
- Tolerant JSON parser: markdown fence strip, full-width punctuation, missing
  closing brackets recovery, single object → array wrap, smart quotes
- Axis-specialized prompts with concrete situational hints per axis
- llama.cpp `json_schema` enforcement (server-side grammar)
- Recursive firewall walk on nested values
- `--smoke-n` for quick acceptance-rate checks

Usage
-----
    # 5-item smoke on compassion (fast acceptance test)
    python synth_data_gen_v2.py --bench data/compassion_v05.jsonl \
        --output data/compassion_smoke.jsonl --axis compassion --smoke-n 5

    # full run (target 100 items)
    python synth_data_gen_v2.py --bench data/compassion_v05.jsonl \
        --output data/compassion_synth_v06.jsonl --axis compassion \
        --n-per-seed 10 --max-output 100
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

LLAMA_BASE = "http://127.0.0.1:8092"
HEADERS = {"Content-Type": "application/json"}

logger = logging.getLogger("synth_gen_v2")


# ── Firewall ─────────────────────────────────────────────────────────

FIREWALL_TERMS = (
    "ai-chan", "ai_chan", "AiChan", "AI-chan",
    "AIちゃん", "アイちゃん", "「ai-chan」", "「Ai」",
)
_FIREWALL_PAT = re.compile("|".join(re.escape(t) for t in FIREWALL_TERMS))


def is_firewall_clean(text: str) -> bool:
    return _FIREWALL_PAT.search(text or "") is None


def walk_strings(obj: Any) -> list[str]:
    """Collect all string leaves from a nested dict/list."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(walk_strings(v))
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            out.extend(walk_strings(x))
    return out


# ── Axis-specialized prompt parts ─────────────────────────────────────

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

# Concrete situational hints per axis — guide the model towards variety
AXIS_SITUATION_HINTS = {
    "family": [
        "高齢の親の物忘れに気付いた場面",
        "兄弟間の介護分担の不平等",
        "配偶者の親 (義父母) との距離感",
        "進学・就職で離れて暮らす子からの相談",
        "孫の前で躾を巡って親と祖父母の意見が割れる",
        "離婚した親と暮らす子供への接し方",
    ],
    "keigo": [
        "上司の上司に対する敬語の二重化",
        "顧客からのクレーム電話での謙譲語",
        "後輩が間違った敬語を使ったときの指摘",
        "「お疲れ様です」と「ご苦労様」の選択",
        "社内メールの締めの言葉",
        "目上の方への依頼文 (お願い申し上げる vs お願いいたします)",
    ],
    "silence": [
        "友人の親族の通夜での挨拶",
        "重病告知を受けた直後の家族への対応",
        "失敗した部下が深く謝罪している場面",
        "災害見舞いの言葉が見つからないとき",
        "離別 (恋愛・友人) を打ち明けられた直後",
        "重い告白 (LGBTQ など) を受けた直後",
    ],
    "compassion": [
        "失業した友人からの相談",
        "うつ病で休職中の同僚への声かけ",
        "認知症の親族への接し方",
        "災害被災者へのボランティア訪問",
        "失恋した若い世代への寄り添い",
        "病気で長期入院している知人へのメッセージ",
    ],
    "local_culture": [
        "京都の言い回し (「考えときます」=断り) の解説",
        "東北のお中元/お歳暮の習慣",
        "茶道での客の正しい所作",
        "通夜・葬儀での香典の地域差",
        "正月の年始挨拶の地域慣習",
        "結婚式での親族の役割分担",
    ],
    "nuance": [
        "「結構です」の二意 (受諾と断り) の使い分け",
        "「ちょっと…」で婉曲に断る場面",
        "「考えておきます」の文化的意味",
        "目上に「了解です」を使うことの是非",
        "「お忙しいところ恐縮ですが」の使いどころ",
        "「私としては」と「個人的には」のニュアンス",
    ],
    "generation_gap": [
        "スマホ操作を教える孫と祖父母",
        "結婚観の親子の世代差",
        "仕事観 (終身雇用 vs ジョブ型) の世代差",
        "SNS マナーへの理解差",
        "コロナ後の距離感の取り方の差",
        "教育方針 (詰め込み vs ゆとり) の親世代対立",
    ],
    "workplace": [
        "上司から不明確な指示を受けた場面",
        "後輩のミスを上司に報告するべきか",
        "退職交渉での切り出し方",
        "セクハラ / パワハラを目撃した同僚への声かけ",
        "メンタル不調の同僚への気遣い",
        "リモートワークでの同僚との距離感",
    ],
}

# JSON Schema for server-side grammar enforcement
SYNTH_JSON_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["context", "expected_qualities", "anti_patterns", "ideal_response_example"],
        "properties": {
            "context": {"type": "string", "minLength": 8, "maxLength": 400},
            "user": {"type": "string", "maxLength": 400},
            "expected_qualities": {
                "type": "array",
                "items": {"type": "string", "minLength": 3, "maxLength": 80},
                "minItems": 2,
                "maxItems": 4,
            },
            "anti_patterns": {
                "type": "array",
                "items": {"type": "string", "minLength": 3, "maxLength": 80},
                "minItems": 2,
                "maxItems": 4,
            },
            "ideal_response_example": {
                "type": "string",
                "minLength": 5,
                "maxLength": 300,
            },
        },
    },
}


# ── llama-server HTTP client ─────────────────────────────────────────


def llama_chat(
    prompt: str,
    *,
    n_predict: int = 1500,
    temperature: float = 0.85,
    use_schema: bool = False,
    timeout: int = 180,
) -> Optional[str]:
    """Call llama-server /v1/chat/completions. Optionally enforce JSON schema."""
    payload: dict[str, Any] = {
        "model": "ai_3b_v14.Q4_K_M.gguf",
        "messages": [
            {
                "role": "system",
                "content": (
                    "あなたは日本語 LLM 評価ベンチマーク作成の専門家です。"
                    "指示に従い、JSON 配列のみを出力します。"
                    "説明文・前置き・コードフェンス (```) は出力しません。"
                    "HTML タグ (<em>, </p>, <br> 等) は絶対に使用しません。"
                    "同じ文字や記号を 3 回以上連続させません (例 「。。。」「...」「<>><>><」)。"
                    "全角の引用符 (「」『』) は使わず、半角の二重引用符 (\") のみ使用します。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": n_predict,
        "temperature": temperature,
        "top_p": 0.9,
        "repeat_penalty": 1.05,
        # Stops: only catch obvious collapse patterns. Avoid stops that may
        # appear in legitimate JSON / Japanese content.
        "stop": ["</em>", "</p>", "</s>", "<|im_end|>", "...........", "。。。。。"],
        "stream": False,
    }
    if use_schema:
        # llama.cpp supports json_schema → GBNF auto-conversion
        payload["json_schema"] = SYNTH_JSON_SCHEMA

    req = urllib.request.Request(
        f"{LLAMA_BASE}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("llama-server failed (temp=%.2f): %s", temperature, e)
        return None


# ── Prompt builder ──────────────────────────────────────────────────


def build_prompt(seed: dict, n_per_seed: int, axis: str, retry_idx: int = 0) -> str:
    """Construct a generation prompt from a seed item, with axis-specific hints."""
    schema_keys = ["context", "user", "expected_qualities", "anti_patterns", "ideal_response_example"]
    seed_summary = {k: seed.get(k) for k in schema_keys if k in seed}
    axis_rule = AXIS_GUIDANCE.get(axis, "seed と同じ軸を厳守.")
    hints = AXIS_SITUATION_HINTS.get(axis, [])
    # Rotate hints based on retry_idx to encourage diversity
    if hints:
        hint_text = "\n".join(f"  - {h}" for h in hints[retry_idx % len(hints):][:4])
        hint_block = f"\n参考になる状況例 (これらと類似でも別場面でも可、 ただし軸厳守):\n{hint_text}\n"
    else:
        hint_block = ""

    return (
        f"あなたは日本語 LLM 評価ベンチマーク作成の専門家. 軸: 「{axis}」.\n"
        f"軸の定義: {axis_rule}\n"
        f"{hint_block}\n"
        "以下が seed (この軸に属する 1 例):\n"
        f"{json.dumps(seed_summary, ensure_ascii=False, indent=2)}\n\n"
        f"上記 seed と同じ軸・同じスキーマで、 別の場面の新しい項目を {n_per_seed} 個作成。\n"
        "厳守:\n"
        f"- 場面 (context) は seed と異なるが、 必ず軸「{axis}」内に収める\n"
        "- expected_qualities, anti_patterns はそれぞれ 2-4 個の文字列リスト\n"
        "- ideal_response_example は 5-300 字の自然な日本語\n"
        "- JSON 配列形式 ([{...}, ...]) のみ出力。 説明文・前置き・コードブロックは禁止\n"
        "- 半角ダブルクォート (\") のみ使用. 全角「」『』は禁止\n"
        "- 「ai-chan」「Ai」 等の固有モデル名は使用禁止\n"
        "\n出力:\n"
    )


# ── Tolerant JSON parser ─────────────────────────────────────────────


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Strip leading fence only
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _full_to_half(text: str) -> str:
    """Convert full-width punctuation that breaks JSON to half-width."""
    table = str.maketrans({
        "：": ":",
        "，": ",",
        "（": "(",
        "）": ")",
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    })
    return text.translate(table)


def _try_close_brackets(text: str) -> str:
    """If text ends mid-array/object, append minimal closers."""
    # Count unmatched
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "[{":
            stack.append(ch)
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
    # Trim trailing trailing comma + close
    text = re.sub(r",\s*$", "", text)
    closer = "".join("]" if c == "[" else "}" for c in reversed(stack))
    return text + closer


_KEY_ALIASES = {
    # Common LLM typos → canonical key
    "antipaterns": "anti_patterns",
    "antipatterns": "anti_patterns",
    "anti-patterns": "anti_patterns",
    "antipatern": "anti_patterns",
    "expectedqualities": "expected_qualities",
    "expected-qualities": "expected_qualities",
    "expected_quality": "expected_qualities",
    "idealresponseexample": "ideal_response_example",
    "ideal-response-example": "ideal_response_example",
    "ideal_response": "ideal_response_example",
}


def _normalize_keys(item: dict) -> dict:
    """Fix common LLM typos in JSON keys."""
    out = {}
    for k, v in item.items():
        canonical = _KEY_ALIASES.get(k, k)
        out[canonical] = v
    return out


def _strip_html(s: str) -> str:
    """Remove HTML tag artifacts the 3B model sometimes leaks into strings."""
    if not isinstance(s, str):
        return s
    s = re.sub(r"</?(?:em|p|br|span|div|strong|b|i|u)>\s*", "", s, flags=re.IGNORECASE)
    return s


def _scrub_item(item: dict) -> dict:
    """Apply key normalization + HTML scrub to all string leaves."""
    item = _normalize_keys(item)
    for k, v in list(item.items()):
        if isinstance(v, str):
            item[k] = _strip_html(v)
        elif isinstance(v, list):
            item[k] = [_strip_html(x) if isinstance(x, str) else x for x in v]
    return item


def _extract_balanced_objects(text: str) -> list[str]:
    """Walk text and yield substrings that are balanced {...} blocks."""
    out: list[str] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start:i + 1])
                start = -1
    return out


def parse_response(text: str) -> list[dict]:
    """Extract JSON items from model output. Multi-stage tolerant fix-ups.

    Strategy:
      1. Strip fences / weird tokens
      2. Try strict parse of whole text or first [...] block
      3. Try tolerant fix-up (smart quotes, full-width, trailing comma)
      4. Try whole-text fix-up + bracket completion for truncated output
      5. As last resort: extract balanced {...} blocks individually (rescues
         partial arrays where the model collapsed mid-stream)

    Every successfully parsed item is scrubbed (key aliases + HTML strip).
    """
    if not text:
        return []
    text = text.replace("</s>", "").replace("<|im_end|>", "")
    text = _strip_code_fence(text)

    def _ret(items: list[dict]) -> list[dict]:
        return [_scrub_item(x) for x in items if isinstance(x, dict)]

    # 1) Direct parse of whole text
    try:
        items = json.loads(text)
        if isinstance(items, list):
            return _ret(items)
        if isinstance(items, dict):
            return _ret([items])
    except json.JSONDecodeError:
        pass

    # 2) Extract first [...] block, greedy
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if m:
        raw = m.group(0)
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return _ret(items)
        except json.JSONDecodeError:
            pass
        # Tolerant fix-up on extracted block
        fixed = _full_to_half(raw)
        fixed = re.sub(r"(?<=[:\[,\s])'", '"', fixed)
        fixed = re.sub(r"'(?=[,\]\s\}])", '"', fixed)
        fixed = re.sub(r",(\s*[\]\}])", r"\1", fixed)
        try:
            items = json.loads(fixed)
            if isinstance(items, list):
                return _ret(items)
        except json.JSONDecodeError:
            pass

    # 3) Whole-text fix-up + bracket completion
    fixed = _full_to_half(text)
    start = fixed.find("[")
    if start >= 0:
        candidate = fixed[start:]
        candidate = re.sub(r",(\s*[\]\}])", r"\1", candidate)
        candidate = _try_close_brackets(candidate)
        try:
            items = json.loads(candidate)
            if isinstance(items, list):
                return _ret(items)
        except json.JSONDecodeError:
            pass

    # 4) RESCUE: walk for balanced {...} blocks (saves partial outputs).
    #    Use ORIGINAL text here — Japanese 「」 in string values is valid content
    #    and full-width→half would corrupt the in-string tracker.
    objects: list[dict] = []
    for blk in _extract_balanced_objects(text):
        # Try strict parse first
        try:
            obj = json.loads(blk)
        except json.JSONDecodeError:
            # Try minor fix-ups on this single block (trailing comma, smart
            # quotes ONLY at structural positions — leave Japanese content alone)
            blk_fix = re.sub(r",(\s*[\]\}])", r"\1", blk)
            try:
                obj = json.loads(blk_fix)
            except json.JSONDecodeError:
                # Last try: full conversion (may corrupt content but worth it
                # for blocks where we already failed)
                blk_full = _full_to_half(blk)
                blk_full = re.sub(r",(\s*[\]\}])", r"\1", blk_full)
                try:
                    obj = json.loads(blk_full)
                except json.JSONDecodeError:
                    continue
        if isinstance(obj, dict):
            objects.append(obj)
    return _ret(objects)


# ── Validate ─────────────────────────────────────────────────────────


REQUIRED_FIELDS = {"context", "expected_qualities", "anti_patterns", "ideal_response_example"}


def validate_item(item: dict) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, "not-a-dict"
    missing = REQUIRED_FIELDS - set(item.keys())
    if missing:
        return False, f"missing:{','.join(sorted(missing))}"
    if not isinstance(item.get("expected_qualities"), list):
        return False, "eq-not-list"
    if not isinstance(item.get("anti_patterns"), list):
        return False, "ap-not-list"
    eq = item.get("expected_qualities", [])
    ap = item.get("anti_patterns", [])
    if len(eq) < 2 or len(eq) > 6:
        return False, f"eq-len:{len(eq)}"
    if len(ap) < 2 or len(ap) > 6:
        return False, f"ap-len:{len(ap)}"
    if not all(isinstance(x, str) and 2 <= len(x) <= 100 for x in eq):
        return False, "eq-item-shape"
    if not all(isinstance(x, str) and 2 <= len(x) <= 100 for x in ap):
        return False, "ap-item-shape"
    ire = item.get("ideal_response_example", "")
    if not isinstance(ire, str) or not (5 <= len(ire) <= 500):
        return False, f"ire-len:{len(ire) if isinstance(ire, str) else 'N/A'}"
    ctx = item.get("context", "")
    if not isinstance(ctx, str) or len(ctx) < 5:
        return False, "ctx-too-short"
    # Firewall on all string leaves
    blob = " ".join(walk_strings(item))
    if not is_firewall_clean(blob):
        return False, "firewall-hit"
    return True, ""


def dedup_key(item: dict) -> str:
    return (str(item.get("context", "")) + "|" + str(item.get("user", "")))[:100]


# ── Main loop ────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, help="seed JSONL path")
    ap.add_argument("--output", required=True, help="output synth JSONL path")
    ap.add_argument("--n-per-seed", type=int, default=3,
                    help="items per seed prompt (3B model collapses with >3-5)")
    ap.add_argument("--max-output", type=int, default=100)
    ap.add_argument("--axis", required=True, help="axis label (family/keigo/...)")
    ap.add_argument("--id-prefix", default=None, help="id prefix (defaults to syn-{axis})")
    ap.add_argument("--retries", type=int, default=3,
                    help="retries per seed with temperature ramp")
    ap.add_argument("--cycles", type=int, default=1,
                    help="how many times to cycle through the seed pool")
    ap.add_argument("--temperature", type=float, default=0.85,
                    help="initial temperature; ramps +0.10 each retry")
    ap.add_argument("--use-schema", action="store_true",
                    help="enable server-side json_schema (often collapses to trivial output; off by default)")
    ap.add_argument("--smoke-n", type=int, default=0,
                    help="if >0, stop after this many items (smoke test)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s [%(levelname)s] %(message)s")

    seeds_path = Path(args.bench)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    id_prefix = args.id_prefix or f"syn-{args.axis}"

    seeds: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                seeds.append(json.loads(line))
    logger.info("loaded %d seeds from %s (axis=%s)", len(seeds), seeds_path, args.axis)

    target = args.smoke_n if args.smoke_n > 0 else args.max_output

    seen_keys: set[str] = set()
    written = 0
    n_attempt = 0
    n_parse_fail = 0
    n_validate_fail = 0
    n_dedup = 0
    fail_reasons: dict[str, int] = {}

    t0 = time.time()
    with out_path.open("w", encoding="utf-8") as fw:
        # Cycle through seed pool up to args.cycles times. Each cycle restarts
        # the seed iteration order, but seen_keys dedup prevents duplicates.
        for cycle_idx in range(args.cycles):
            if written >= target:
                break
            if args.cycles > 1:
                logger.info("=== cycle %d/%d (written so far: %d) ===",
                            cycle_idx + 1, args.cycles, written)
            for seed_idx, seed in enumerate(seeds):
                if written >= target:
                    break
                # Per-seed retry loop with temperature ramp
                for retry in range(args.retries):
                    if written >= target:
                        break
                    # Cycle index slightly shifts base temp for diversity
                    temp = args.temperature + retry * 0.10 + cycle_idx * 0.05
                    # Rotate axis hints by seed_idx + cycle for variety
                    rot = retry + cycle_idx * 2
                    prompt = build_prompt(seed, args.n_per_seed, axis=args.axis, retry_idx=rot)
                    response = llama_chat(
                        prompt, n_predict=2000, temperature=temp,
                        use_schema=args.use_schema,
                    )
                    n_attempt += 1
                    if response is None:
                        continue
                    items = parse_response(response)
                    if not items:
                        n_parse_fail += 1
                        logger.debug("parse fail seed[%d] retry=%d: %r",
                                     seed_idx, retry, response[:300])
                        continue

                    accepted_this_call = 0
                    for item in items:
                        ok, reason = validate_item(item)
                        if not ok:
                            n_validate_fail += 1
                            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                            continue
                        k = dedup_key(item)
                        if k in seen_keys:
                            n_dedup += 1
                            continue
                        seen_keys.add(k)
                        new_item = {
                            "id": f"{id_prefix}-{written:04d}",
                            "axis": args.axis,
                            **item,
                            "synth_seed_id": seed.get("id"),
                        }
                        fw.write(json.dumps(new_item, ensure_ascii=False) + "\n")
                        fw.flush()
                        written += 1
                        accepted_this_call += 1
                        if written >= target:
                            break

                    # If we got any accepted items, no need to retry this seed
                    if accepted_this_call > 0:
                        break

                if seed_idx % 5 == 0:
                    elapsed = time.time() - t0
                    rate = written / max(1, elapsed)
                    logger.info(
                        "progress: cycle=%d seed %d/%d → %d written (parse_fail=%d val_fail=%d dedup=%d) [%.2f it/s]",
                        cycle_idx + 1, seed_idx + 1, len(seeds), written,
                        n_parse_fail, n_validate_fail, n_dedup, rate
                    )

    elapsed = time.time() - t0
    logger.info(
        "done: %d items in %s (attempts=%d parse_fail=%d val_fail=%d dedup=%d, %.0f sec)",
        written, out_path, n_attempt, n_parse_fail, n_validate_fail, n_dedup, elapsed,
    )
    if fail_reasons:
        top = sorted(fail_reasons.items(), key=lambda kv: -kv[1])[:8]
        logger.info("top validate fail reasons: %s",
                    ", ".join(f"{k}={v}" for k, v in top))
    return 0 if written > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
