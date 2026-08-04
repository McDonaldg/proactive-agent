"""収集層。LLM は一切呼ばない。ここで金を使うと台無しになる。

出力: data/pool.jsonl （URL ハッシュで重複排除済み）
"""
import hashlib
import os
import sys
import time

import feedparser
import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.lib import store  # noqa: E402

RETENTION_DAYS = 21
HN_API = "https://hn.algolia.com/api/v1/search_by_date"


def uid(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def from_rss(src):
    d = feedparser.parse(src["url"])
    out = []
    for e in d.entries[:30]:
        link = e.get("link")
        if not link:
            continue
        out.append({
            "uid": uid(link),
            "src": src["id"],
            "weight": src.get("weight", 1.0),
            "title": e.get("title", "")[:200],
            "url": link,
            "summary": (e.get("summary", "") or "")[:600],
            "ts": store.stamp(),
        })
    return out


def from_youtube(ch):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
    src = {"id": ch["id"], "url": url, "weight": ch.get("weight", 1.0)}
    return from_rss(src)


def from_hn(cfg):
    cutoff = int(time.time()) - cfg["window_hours"] * 3600
    out = []
    for kw in cfg["keywords"]:
        try:
            r = requests.get(HN_API, timeout=30, params={
                "query": kw,
                "tags": "story",
                "numericFilters": f"created_at_i>{cutoff},points>{cfg['min_points']}",
                "hitsPerPage": 10,
            })
            r.raise_for_status()
        except requests.RequestException:
            continue
        for h in r.json().get("hits", []):
            link = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append({
                "uid": uid(link),
                "src": "hackernews",
                "weight": cfg.get("weight", 1.0),
                "title": (h.get("title") or "")[:200],
                "url": link,
                "summary": f"HN {h.get('points', 0)}pts / {h.get('num_comments', 0)}comments",
                "ts": store.stamp(),
            })
        time.sleep(0.2)
    return out


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "feeds.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    items = []
    for s in cfg.get("rss", []):
        items += from_rss(s)
    for c in cfg.get("youtube", []):
        if "xxxx" in c["channel_id"]:
            continue  # プレースホルダはスキップ
        items += from_youtube(c)
    if cfg.get("hackernews"):
        items += from_hn(cfg["hackernews"])

    # 既存 pool と提案済みを除外
    seen = {r["uid"] for r in store.read("pool")}
    seen |= {r.get("uid") for r in store.read("proposals", limit=200)}

    fresh, added = [], 0
    for it in items:
        if it["uid"] in seen:
            continue
        seen.add(it["uid"])
        store.append("pool", it)
        added += 1
    print(f"collected={len(items)} new={added}")


if __name__ == "__main__":
    main()
