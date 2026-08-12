"""Discord I/O.

重要な制約:
  Webhook は「投稿」しかできない。リアクションや返信を読むには Bot トークンが要る。
  よってこのプロジェクトは Webhook ではなく Bot トークンで統一する。

Bot に必要な権限:
  Send Messages / Read Message History / Add Reactions
"""
import json
import os
import time
import requests

API = "https://discord.com/api/v10"
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL = os.environ.get("DISCORD_CHANNEL_ID", "")

# 否認理由タグ。ここを変えたら profile.json 側の補正ロジックも合わせること
TAGS = {
    "✅": "approve",
    "⏰": "no_time",
    "🔁": "already_known",
    "🎯": "off_target",
    "💰": "too_costly",
}


def _h():
    return {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}


def post(content):
    r = requests.post(f"{API}/channels/{CHANNEL}/messages",
                      headers=_h(), json={"content": content}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def post_file(content, image_bytes, filename="proposal.png"):
    """スライド画像を添付して投稿する。content は画像の下に出す添え文。"""
    payload = {"payload_json": json.dumps({"content": content}, ensure_ascii=False)}
    files = {"files[0]": (filename, image_bytes, "image/png")}
    r = requests.post(f"{API}/channels/{CHANNEL}/messages",
                      headers={"Authorization": f"Bot {TOKEN}"},
                      data=payload, files=files, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def seed_reactions(message_id):
    """押しやすいように先に絵文字を並べておく。これが UX の 8 割。"""
    for emoji in TAGS:
        requests.put(
            f"{API}/channels/{CHANNEL}/messages/{message_id}/reactions/{emoji}/@me",
            headers=_h(), timeout=30)
        time.sleep(0.3)  # レート制限回避


def get_reactions(message_id):
    """人間が押したタグだけを返す（Bot 自身の初期リアクションは除外）。"""
    r = requests.get(f"{API}/channels/{CHANNEL}/messages/{message_id}",
                     headers=_h(), timeout=30)
    r.raise_for_status()
    out = []
    for rc in r.json().get("reactions", []):
        emoji = rc["emoji"]["name"]
        # count>1 = Bot の初期リアクションに人間が乗った
        if emoji in TAGS and rc["count"] > 1:
            out.append(TAGS[emoji])
    return out


def get_replies(message_id, after_id=None):
    """対象メッセージへの返信本文を集める。自由入力の受け口。"""
    params = {"limit": 100}
    if after_id:
        params["after"] = after_id
    r = requests.get(f"{API}/channels/{CHANNEL}/messages",
                     headers=_h(), params=params, timeout=30)
    r.raise_for_status()
    replies = []
    for m in r.json():
        if m.get("author", {}).get("bot"):
            continue
        ref = m.get("message_reference") or {}
        if ref.get("message_id") == message_id:
            replies.append(m["content"])
    return replies
