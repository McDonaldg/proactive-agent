"""JSONL ストア。追記のみ・全読みしない、が原則。"""
import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def now_jst():
    return datetime.now(JST)


def stamp():
    return now_jst().isoformat(timespec="seconds")


def path(name):
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, f"{name}.jsonl")


def append(name, obj):
    with open(path(name), "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read(name, limit=None, where=None):
    """末尾から limit 件。where は dict の述語関数。

    全件ロードを避けるため、必要なら limit を必ず指定すること。
    """
    p = path(name)
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if where and not where(o):
                continue
            rows.append(o)
    return rows[-limit:] if limit else rows


def rewrite(name, rows):
    """interests の status 更新など、書き換えが必要なときだけ使う。"""
    with open(path(name), "w", encoding="utf-8") as f:
        for o in rows:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def load_json(rel):
    with open(os.path.join(os.path.dirname(__file__), "..", "..", rel), encoding="utf-8") as f:
        return json.load(f)


def save_json(rel, obj):
    with open(os.path.join(os.path.dirname(__file__), "..", "..", rel), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
