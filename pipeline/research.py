"""Free news gathering: Bing News RSS, Google News RSS, Reddit, plus a hand-kept facts file."""
from __future__ import annotations

import html
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
import yaml

UA = {"User-Agent": "Mozilla/5.0 (autoshorts research bot)"}
ROOT = Path(__file__).resolve().parents[1]


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def rss_items(query: str, limit=15):
    out = []
    feeds = [
        ("bing", f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss"),
        ("google", f"https://news.google.com/rss/search?q={quote_plus(query)}+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ]
    for name, url in feeds:
        try:
            r = requests.get(url, headers=UA, timeout=15)
            feed = feedparser.parse(r.content)
            for e in feed.entries[:limit]:
                src = getattr(e, "source", {}).get("title", "") if hasattr(e, "source") else ""
                out.append({"title": _clean(e.get("title", "")), "summary": _clean(e.get("summary", ""))[:500],
                            "url": e.get("link", ""), "source": src or name,
                            "published": e.get("published", "")})
        except Exception as ex:  # one feed failing shouldn't stop the run
            print(f"[research] {name} feed failed: {ex}")
    return out


def reddit_items(sub="GTA6", limit=10):
    try:
        r = requests.get(f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}", headers=UA, timeout=15)
        r.raise_for_status()
        return [{"title": c["data"]["title"], "summary": _clean(c["data"].get("selftext", ""))[:400],
                 "url": "https://reddit.com" + c["data"]["permalink"], "source": f"r/{sub} (community post, unverified)",
                 "published": time.strftime("%Y-%m-%d", time.gmtime(c["data"]["created_utc"]))}
                for c in r.json()["data"]["children"] if not c["data"].get("stickied")]
    except Exception as ex:
        print(f"[research] reddit failed: {ex}")
        return []


def article_text(url: str, max_chars=2500) -> str:
    """Grab the paragraph text of an article so the script has real details to work with."""
    if "news.google.com" in url:
        return ""
    try:
        r = requests.get(url, headers=UA, timeout=15)
        paras = re.findall(r"<p[^>]*>(.*?)</p>", r.text, flags=re.S | re.I)
        text = " ".join(_clean(p) for p in paras if len(_clean(p)) > 60)
        return text[:max_chars]
    except Exception:
        return ""


def load_facts():
    p = ROOT / "facts.yaml"
    return yaml.safe_load(p.read_text()).get("facts", []) if p.exists() else []


def gather(queries, used_urls: set, n_articles=3):
    items, seen = [], set()
    for q in queries:
        for it in rss_items(q):
            key = it["title"].lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
    items += reddit_items()
    fresh = [i for i in items if i["url"] not in used_urls]
    # enrich the first few fresh, non-Reddit articles with body text
    k = 0
    for it in fresh:
        if k >= n_articles:
            break
        if "reddit" not in it["source"]:
            it["body"] = article_text(it["url"])
            if it["body"]:
                k += 1
    return {"news": fresh[:25], "facts": load_facts()}
