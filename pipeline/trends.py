"""What's trending right now, filtered for a broad Shorts audience.

Sources (all free): Google Trends daily RSS (US) and YouTube's "most popular" charts per
category (uses the channel's existing YouTube login). Saved to state/trends.json, which the
daily script writer reads to pick topics.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state" / "trends.json"
UA = {"User-Agent": "Mozilla/5.0 (autoshorts trends)"}

# Topics that don't fit a fun, broad Shorts channel (or need care we can't automate).
AVOID = re.compile(r"\b(killed|kill|dies|died|dead|death|murder|shooting|shot|stabb|war|attack|bomb|terror|"
                   r"crash|victim|abuse|assault|suicide|overdose|arrest|charged|trial|lawsuit|election|"
                   r"senate|congress|president|trump|biden|democrat|republican|vote|israel|gaza|ukraine|"
                   r"russia|porn|nude|onlyfans|sex|hostage|funeral|obituary|missing)\b", re.I)
YT_CATEGORIES = {"20": "gaming", "24": "entertainment", "17": "sports", "23": "comedy", "28": "tech", "10": "music"}


def google_trends(geo="US"):
    try:
        r = requests.get(f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, timeout=20)
        feed = feedparser.parse(r.content)
        out = []
        for e in feed.entries[:30]:
            news = []
            for k in ("ht_news_item_title",):
                if e.get(k):
                    news.append({"title": e.get(k), "url": e.get("ht_news_item_url", ""),
                                 "source": e.get("ht_news_item_source", "")})
            out.append({"query": e.get("title", ""), "traffic": e.get("ht_approx_traffic", ""), "news": news})
        return out
    except Exception as ex:
        print(f"[trends] google trends failed: {ex}")
        return []


def youtube_trending():
    if not os.environ.get("YT_REFRESH_TOKEN"):
        return []
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"])
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        out = []
        for cat, name in YT_CATEGORIES.items():
            try:
                r = yt.videos().list(part="snippet,statistics", chart="mostPopular", regionCode="US",
                                     videoCategoryId=cat, maxResults=15).execute()
            except Exception as ex:
                if "insufficient" in str(ex).lower() or "403" in str(ex):
                    print("[trends] YouTube trending needs read access; skipping (Google Trends + web research still used)")
                    return out
                continue
            for v in r.get("items", []):
                sn = v["snippet"]
                out.append({"title": sn["title"], "channel": sn["channelTitle"], "category": name,
                            "views": int(v.get("statistics", {}).get("viewCount", 0)),
                            "tags": sn.get("tags", [])[:8]})
        return out
    except Exception as ex:
        print(f"[trends] youtube trending failed: {ex}")
        return []


def safe(text):
    return not AVOID.search(text or "")


def refresh(max_age_h=6):
    if OUT.exists():
        old = json.loads(OUT.read_text())
        if time.time() - old.get("ts", 0) < max_age_h * 3600:
            return old
    g = [t for t in google_trends() if safe(t["query"]) and all(safe(n["title"]) for n in t["news"])]
    y = [v for v in youtube_trending() if safe(v["title"])]
    data = {"ts": time.time(), "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "google_trends": g, "youtube_trending": y}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1))
    print(f"[trends] {len(g)} Google trends, {len(y)} YouTube trending videos saved")
    return data
