"""フィードバック層。前回の提案からリアクションと返信を回収する。

  リアクション -> decisions.jsonl + profile.json の重み補正
  返信        -> Haiku で request / profile_update に分類 -> interests.jsonl
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.lib import store, llm, discord  # noqa: E402

CLASSIFY_SYSTEM = """ユーザーの自由入力を分類する。JSON のみ出力。

{"type":"request|profile_update",
 "normalized":"意図を1文に整理",
 "queries":["web検索クエリ",...最大3件],
 "topic":"該当しそうな既存トピック名 or null"}

判定基準:
- 特定の課題・作りたいものへの言及 -> request
- 関心領域そのものの変化の宣言 -> profile_update
- 判断がつかない場合は必ず request（安全側）"""


def classify(raw, topics):
    out = llm.call(
        llm.MODEL_CHEAP,
        CLASSIFY_SYSTEM,
        f"既存トピック: {', '.join(topics)}\n\n入力: {raw}",
        max_tokens=400, json_mode=True,
    )
    return out or {"type": "request", "normalized": raw, "queries": [raw], "topic": None}


def adjust_constraints(profile, tags):
    """否認タグに応じて制約を機械的に補正する。LLM は使わない。

    no_time/too_costly は特定のカードではなく提案全体への不満なので、
    そのメッセージに付いたリアクションかどうかに関わらず一律に効かせる。
    """
    c = profile["constraints"]
    changed = []

    if "no_time" in tags and c["max_minutes"] > 20:
        c["max_minutes"] = max(20, int(c["max_minutes"] * 0.7))
        changed.append(f"max_minutes -> {c['max_minutes']}")

    if "too_costly" in tags:
        c["max_cost_jpy"] = 0
        changed.append("max_cost_jpy -> 0")

    return changed


def adjust_topic_weight(profile, card, tags):
    """1カード=1メッセージなので、そのカードに付いたリアクションだけで
    そのカードのトピックの重みを補正できる（他カードを巻き込まない）。"""
    changed = []
    t = card.get("topic")
    if not t or t not in profile["topics"]:
        return changed

    if "off_target" in tags:
        profile["topics"][t]["weight"] = round(
            max(0.1, profile["topics"][t]["weight"] * 0.85), 2)
        changed.append(f"{t} weight down")

    if "approve" in tags:
        profile["topics"][t]["weight"] = round(
            min(2.0, profile["topics"][t]["weight"] * 1.1), 2)
        changed.append(f"{t} weight up")

    return changed


def main():
    latest = store.read("proposals", limit=1)
    if not latest:
        print("no proposal yet")
        return
    prop = latest[0]
    if prop.get("harvested"):
        print("already harvested")
        return

    profile = store.load_json("config/profile.json")

    # 1提案1メッセージなので、カードごとにリアクション/返信を個別に回収する。
    per_card_tags = []
    replies = []
    for card in prop["cards"]:
        mid = card["message_id"]
        tags = discord.get_reactions(mid)
        replies += discord.get_replies(mid)
        per_card_tags.append((card, tags))

        store.append("decisions", {
            "ts": store.stamp(),
            "message_id": mid,
            "slot": card["slot"],
            "card_title": card["title"],
            "tags": tags,
        })

    all_tags = [t for _, tags in per_card_tags for t in tags]
    changed = adjust_constraints(profile, all_tags)
    for card, tags in per_card_tags:
        changed += adjust_topic_weight(profile, card, tags)

    # 自由入力の取り込み
    added = []
    for raw in replies:
        r = classify(raw, list(profile["topics"].keys()))
        if r["type"] == "profile_update":
            t = r.get("topic")
            if t and t in profile["topics"]:
                profile["topics"][t]["weight"] = round(
                    min(2.0, profile["topics"][t]["weight"] * 1.3), 2)
                changed.append(f"{t} weight up (declared)")
        else:
            iid = f"i_{store.now_jst():%Y%m%d}_{len(added) + 1:02d}"
            store.append("interests", {
                "id": iid, "ts": store.stamp(), "raw": raw,
                "normalized": r["normalized"], "queries": r.get("queries", []),
                "topic": r.get("topic"), "status": "open", "attempts": 0,
            })
            added.append(iid)

    store.save_json("config/profile.json", profile)

    # 打ち切ったリクエストは黙って消さず、必ず報告する
    exhausted = [r for r in store.read("interests") if r.get("status") == "exhausted"
                 and not r.get("reported")]
    if exhausted:
        names = "、".join(r["normalized"] for r in exhausted)
        discord.post(f"この線は当たりがありませんでした: {names}\n"
                     f"角度を変えたい場合は返信してください。")
        rows = store.read("interests")
        for r in rows:
            if r.get("status") == "exhausted":
                r["reported"] = True
        store.rewrite("interests", rows)

    prop["harvested"] = True
    props = store.read("proposals")
    props[-1] = prop
    store.rewrite("proposals", props)

    print(f"tags={all_tags} replies={len(replies)} new_requests={added} adj={changed}")


if __name__ == "__main__":
    main()
