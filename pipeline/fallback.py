"""No-AI fallbacks so every scheduled run still posts something accurate.

1. news_from_headline: turns a fresh, on-topic headline into a short news-flash video.
2. pick_bank: a hand-written, fact-checked script from bank/ that hasn't been used yet.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _clean_headline(t: str) -> str:
    t = re.sub(r"\s+[-|\u2013\u2014]\s+[^-|\u2013\u2014]{2,40}$", "", t).strip()  # drop " - Source"
    return t


def _sentences(text: str, max_words=28):
    s = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for x in s:
        w = x.split()
        if 6 <= len(w) <= max_words:
            out.append(x)
    return out


def news_from_headline(research: dict, cfg: dict, used_urls: set):
    keys = [k.lower() for k in ("GTA 6", "GTA VI", "Grand Theft Auto VI", "GTA6")]
    for it in research.get("news", []):
        title = _clean_headline(it.get("title", ""))
        if it.get("url") in used_urls or "reddit" in it.get("source", "").lower():
            continue
        if not any(k in title.lower() for k in keys) or not (5 <= len(title.split()) <= 18):
            continue
        detail = _sentences(it.get("body") or it.get("summary") or "")
        if not detail:
            continue
        hook = " ".join(title.split()[:6]).rstrip(",:;")
        source = it.get("source") or "news reports"
        scenes = [
            {"type": "hook", "text": hook, "say": "GTA 6 news you need to know."},
            {"type": "text", "text": " ".join(title.split()[:9]), "sub": f"via {source}"[:40], "say": title + "."},
            {"type": "text", "text": "Here's what we know", "say": detail[0]},
        ]
        if len(detail) > 1:
            scenes.append({"type": "text", "text": "And there's more", "say": detail[1]})
        scenes.append({"type": "outro", "text": "What do you think?", "cta": "Comment below",
                       "say": "What do you think about this? Tell me in the comments."})
        return {"format": "news_flash", "kicker": "GTA 6 news", "title": ((title if len(title) <= 80 else title[:80].rsplit(" ", 1)[0] + "...") + " #gta6 #shorts"),
                "description": f"Source: {source} - {it.get('url', '')}",
                "hashtags": ["#gta6", "#gtavi", "#gtanews", "#gaming", "#shorts"],
                "source_urls": [it.get("url", "")], "scenes": scenes}
    return None


def pick_bank(used: list):
    files = sorted((ROOT / "bank").glob("*.json"))
    fresh = [f for f in files if f.stem not in used] or files  # recycle once all are used
    f = random.choice(fresh)
    d = json.loads(f.read_text())
    d["bank_id"] = f.stem
    return d
