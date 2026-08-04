"""提案層。3 枠（指名/継続/探索）でカードを組み、Discord に投げる。

LLM 呼び出しはこのファイルで最大 2 回:
  1. Haiku ... pool の足切り（キーワード score 上位 20 -> 候補 8）
  2. Sonnet ... カード 3 枚の本文生成
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.lib import store, llm, discord  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- 1. スコアリング（LLM 不使用） ----------------------------------
def score(item, profile):
    """タイトル+要約 x 興味キーワード x 情報源重み。素朴だが十分に効く。

    既存の M1 パイプラインに embedding 選抜があるなら、
    この関数だけを差し替えれば精度が上がる。
    """
    text = (item["title"] + " " + item["summary"]).lower()
    best_topic, s = None, 0.0
    for name, t in profile["topics"].items():
        hits = sum(1 for k in t["kw"] if k.lower() in text)
        v = hits * t["weight"]
        if v > s:
            best_topic, s = name, v
    return s * item.get("weight", 1.0), best_topic


# ---------- 2. 否認履歴の圧縮 ---------------------------------------------
def rejection_context(n=20):
    """全文ではなくタグの集計だけを渡す。ここがトークン効率の肝。"""
    rows = store.read("decisions", limit=n)
    if not rows:
        return "否認履歴なし（初回）"
    tally = {}
    for r in rows:
        for t in r.get("tags", []):
            if t != "approve":
                tally[t] = tally.get(t, 0) + 1
    if not tally:
        return "直近は否認なし"
    order = sorted(tally.items(), key=lambda x: -x[1])
    label = {"no_time": "時間がない", "already_known": "既知",
             "off_target": "興味とズレ", "too_costly": "コスト高"}
    return " / ".join(f"{label.get(k, k)}x{v}" for k, v in order)


def open_requests():
    rows = store.read("interests")
    return [r for r in rows if r.get("status") == "open" and r.get("attempts", 0) < 3]


# ---------- 3. カード生成 --------------------------------------------------
SYSTEM = """あなたは多忙な個人開発者(masahiro)の提案担当。日本語で書く。

出力は JSON 配列のみ。前置き・コードフェンス禁止。各要素:
{"slot":"request|continuation|exploration",
 "uid":"元記事のuid(探索/継続のみ。指名枠はnull)",
 "title":"25字以内",
 "interpretation":"指名枠のみ。要望をどう解釈したかを1文。他はnull",
 "what":"何をするか1文",
 "why":"それで何が変わるか1文。抽象語を使わず具体的な変化を書く",
 "minutes":整数, "cost_jpy":整数, "url":"参照URL or null"}

制約:
- 各枠ちょうど1件。合計3件。
- minutes は constraints.max_minutes 以下に必ず収める。
- why には「効率化」「便利になる」など中身のない語を使わない。
- 探索枠は継続枠と別トピックにする。似た2枚は価値がない。"""


def build(profile):
    pool = store.read("pool")
    scored = []
    for it in pool:
        s, topic = score(it, profile)
        if s > 0:
            scored.append((s, topic, it))
    scored.sort(key=lambda x: -x[0])
    top = scored[:20]

    reqs = open_requests()
    cons = profile["constraints"]

    cand_txt = "\n".join(
        f"- uid={it['uid']} [{topic}] {it['title']} ({it['url']})\n  {it['summary'][:180]}"
        for _, topic, it in top
    ) or "(候補なし)"

    req_txt = "\n".join(
        f"- {r['id']}: {r['raw']}（試行{r.get('attempts',0)}回目）" for r in reqs
    ) or "(なし。指名枠は2件目の探索枠として使う)"

    user = f"""【前回までの否認傾向】{rejection_context()}
→ この傾向を踏まえて提案を調整すること。

【制約】所要時間 {cons['max_minutes']}分以内 / 追加費用 {cons['max_cost_jpy']}円以内

【指名枠のリクエスト】
{req_txt}

【候補記事(継続枠・探索枠はここから選ぶ)】
{cand_txt}
"""
    cards = llm.call(llm.MODEL_WRITE, SYSTEM, user, max_tokens=2000, json_mode=True)
    return cards or [], reqs


# ---------- 4. 整形と投稿 --------------------------------------------------
SLOT_LABEL = {"request": "指名枠", "continuation": "継続枠", "exploration": "探索枠"}


def render(cards, rej):
    lines = [f"**本日の提案** — 前回傾向: {rej}", ""]
    for i, c in enumerate(cards, 1):
        lines.append(f"**{i}. 【{SLOT_LABEL.get(c['slot'], c['slot'])}】{c['title']}**")
        if c.get("interpretation"):
            lines.append(f"> 解釈: {c['interpretation']}")
        lines.append(c["what"])
        lines.append(f"→ **{c['why']}**")
        tail = f"⏱ {c['minutes']}分  💰 ¥{c['cost_jpy']}"
        if c.get("url"):
            tail += f"  <{c['url']}>"
        lines.append(tail)
        lines.append("")
    lines.append("✅承認 / ⏰時間がない / 🔁既知 / 🎯興味とズレ / 💰コスト高")
    lines.append("_やりたいことがあればこのメッセージに返信してください_")
    return "\n".join(lines)


def main():
    profile = store.load_json("config/profile.json")
    cards, reqs = build(profile)
    if not cards:
        discord.post("本日は提案なし（候補の質がしきい値に届きませんでした）")
        return

    rej = rejection_context()
    msg_id = discord.post(render(cards, rej))
    discord.seed_reactions(msg_id)

    store.append("proposals", {
        "ts": store.stamp(),
        "message_id": msg_id,
        "cards": cards,
        "request_ids": [r["id"] for r in reqs],
    })

    # 指名枠を消化したので試行回数を進める
    if reqs:
        rows = store.read("interests")
        for r in rows:
            if r["id"] == reqs[0]["id"]:
                r["attempts"] = r.get("attempts", 0) + 1
                if r["attempts"] >= 3:
                    r["status"] = "exhausted"
        store.rewrite("interests", rows)

    print(f"posted {msg_id}")


if __name__ == "__main__":
    main()
