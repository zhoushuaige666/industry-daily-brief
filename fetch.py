import feedparser
import requests
import json
import re
import os
import html
import hashlib
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
DATA_FILE = "data.json"
MAX_AGE_DAYS = 30
MAX_ITEMS = 2000

SOURCES = [
    {"name": "36氪", "url": "https://36kr.com/feed", "category": "商业"},
    {"name": "少数派", "url": "https://sspai.com/feed", "category": "科技"},
    {"name": "Solidot", "url": "https://www.solidot.org/index.rss", "category": "科技"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "category": "科技"},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "category": "商业"},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss.xml", "category": "创投"},
    {"name": "极客公园", "url": "https://www.geekpark.net/rss", "category": "AI"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (IndustryDailyBot/1.0)"}


def gen_id(link):
    return hashlib.sha1((link or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def clean_text(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", "", str(raw))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def parse_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(CST)


def fetch_latest():
    items = []
    ok = []
    failed = []
    for src in SOURCES:
        try:
            resp = requests.get(src["url"], headers=HEADERS, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            count = 0
            for e in feed.entries[:10]:
                title = clean_text(e.get("title", ""))
                link = e.get("link", "")
                summary = clean_text(e.get("summary", e.get("description", "")))
                dt = parse_time(e)
                items.append({
                    "id": gen_id(link),
                    "title": title,
                    "url": link,
                    "source": src["name"],
                    "category": src["category"],
                    "published": dt.astimezone(CST).isoformat(),
                    "summary": summary,
                })
                count += 1
            if count > 0:
                ok.append(src["name"] + "(" + str(count) + ")")
            else:
                failed.append(src["name"])
        except Exception as ex:
            failed.append(src["name"] + ":" + type(ex).__name__)
    return items, ok, failed


def fetch_hot():
    hot = []
    try:
        r = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers=HEADERS, timeout=15)
        ids = r.json()[:20]
        for hid in ids:
            try:
                item = requests.get(
                    "https://hacker-news.firebaseio.com/v0/item/" + str(hid) + ".json",
                    headers=HEADERS, timeout=10).json()
                if not item:
                    continue
                hot.append({
                    "id": gen_id("hn-" + str(hid)),
                    "title": item.get("title", ""),
                    "url": item.get("url") or ("https://news.ycombinator.com/item?id=" + str(hid)),
                    "score": item.get("score", 0),
                    "by": item.get("by", ""),
                    "comments": item.get("descendants", 0),
                })
            except Exception:
                continue
    except Exception as ex:
        print("HN fetch failed:", ex)
    return hot


def load_old_data():
    if not os.path.exists(DATA_FILE):
        return {"items": [], "hot": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"items": [], "hot": []}
        items = data.get("items", [])
        if not isinstance(items, list):
            items = []
        for it in items:
            if not it.get("id"):
                it["id"] = gen_id(it.get("url", ""))
        data["items"] = items
        return data
    except Exception:
        return {"items": [], "hot": []}


def merge_items(old_items, new_items):
    seen = set()
    merged = []
     for it in old_items + new_items:
         iid = it.get("id", "")
         if iid and iid not in seen:
             seen.add(iid)
             merged.append(it)
     merged.sort(key=lambda x: x.get("published", ""), reverse=True)
     cutoff = datetime.now(CST) - timedelta(days=MAX_AGE_DAYS)
     merged = [it for it in merged if parse_iso(it.get("published", "")) >= cutoff]
     return merged[:MAX_ITEMS]
 def main():
     old = load_old_data()
     new_items, ok, failed = fetch_latest()
     hot = fetch_hot()
     merged = merge_items(old.get("items", []), new_items)
     data = {
         "generated_at": datetime.now(CST).isoformat(),
         "items": merged,
         "hot": hot,
         "sources_ok": ok,
         "sources_failed": failed,
         "total": len(merged),
     }
     with open(DATA_FILE, "w", encoding="utf-8") as f:
json.dump(data, f, ensure_ascii=False, indent=2)
     print("OK:", len(merged), "items total,", len(new_items), "new,", len(hot), "hot")
 if __name__ == "__main__":
     main()
