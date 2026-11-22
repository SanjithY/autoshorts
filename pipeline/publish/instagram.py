"""Instagram Reels via the free Instagram API (Instagram Login), using resumable binary upload."""
from __future__ import annotations

import os
import time

import requests

from . import tokens

GRAPH = "https://graph.instagram.com/v21.0"


def _token():
    tok = tokens.get("IG_ACCESS_TOKEN")
    # long-lived tokens last 60 days; refreshing each run keeps them alive indefinitely
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30).json()
    if r.get("access_token"):
        tok = r["access_token"]
        tokens.put("IG_ACCESS_TOKEN", tok)
    return tok


def upload(video_path: str, meta: dict, cfg: dict) -> dict:
    tok = _token()
    uid = os.environ["IG_USER_ID"]
    caption = (meta["title"].replace("#shorts", "").strip() + "\n\n" + meta.get("description", "") +
               "\n\n" + " ".join(meta.get("hashtags", [])))[:2200]
    c = requests.post(f"{GRAPH}/{uid}/media", params={"access_token": tok}, timeout=30, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true"}).json()
    if "id" not in c:
        raise RuntimeError(f"Instagram container failed: {c}")
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        up = requests.post(c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{c['id']}",
                           data=fh.read(), timeout=300,
                           headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    up.raise_for_status()
    for _ in range(40):
        time.sleep(8)
        st = requests.get(f"{GRAPH}/{c['id']}", params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {st}")
    pub = requests.post(f"{GRAPH}/{uid}/media_publish", params={"access_token": tok},
                        data={"creation_id": c["id"]}, timeout=30).json()
    if "id" not in pub:
        raise RuntimeError(f"Instagram publish failed: {pub}")
    return {"platform": "instagram", "id": pub["id"]}
