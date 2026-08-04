"""LLM 呼び出しの単一窓口。

モデル選択をここに集約することで、
「どの工程にいくら払っているか」がこのファイルを見るだけで分かる状態を保つ。
"""
import os
import json
import anthropic
from . import store

# ---- モデル使い分け ----------------------------------------------------
# 判定・分類・足切り: 出力が短く、判断基準が明示的 -> Haiku
MODEL_CHEAP = "claude-haiku-4-5-20251001"
# 提案文の生成: ここだけ品質が体験に直結する -> Sonnet
MODEL_WRITE = "claude-sonnet-5"
# 実行層(Claude Code)側で設計判断を伴う場合のみ Opus を指定する。
# 定期実行のパイプライン内では Opus を使わない。
MODEL_HEAVY = "claude-opus-5"
# ------------------------------------------------------------------------

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call(model, system, user, max_tokens=1500, json_mode=False):
    """1 回の完了。usage を必ず記録する。"""
    msg = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")

    store.append("usage", {
        "ts": store.stamp(),
        "model": model,
        "in": msg.usage.input_tokens,
        "out": msg.usage.output_tokens,
    })

    if not json_mode:
        return text

    # ```json フェンスを剥がしてからパース
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("\n", 1)
        cleaned = parts[1].rsplit("```", 1)[0].strip() if len(parts) > 1 else ""

    if not cleaned:
        # 応答が空だった。修復しようがないのでここで諦める。
        # (空文字を Haiku に渡すと 400 エラーになるため、渡さない)
        print(f"[llm.call] empty response from {model}, raw_text={text!r}")
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 1 度だけ Haiku に修復させる。それでも駄目なら諦めて呼び出し側に返す
        fixed = call(
            MODEL_CHEAP,
            "壊れた JSON を修復する。JSON 本体のみを出力し、前置き・コードフェンスを付けない。",
            cleaned,
            max_tokens=max_tokens,
        )
        try:
            return json.loads(fixed.strip()) if fixed else None
        except json.JSONDecodeError:
            print(f"[llm.call] repair failed, cleaned={cleaned!r}")
            return None
