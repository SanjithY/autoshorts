"""TikTok Direct Post via the free Content Posting API (needs app audit for public posts)."""
from __future__ import annotations

import os
import time

import requests

from . import tokens

API = "https://open.tiktokapis.com/v2"


def _access_token():
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": tokens.get("TIKTOK_REFRESH_TOKEN")},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    if data.get("refresh_token"):
        tokens.put("TIKTOK_REFRESH_TOKEN", data["refresh_token"])  # TikTok may rotate it
    return data["access_token"]


def upload(video_path: str, meta: dict, cfg: dict) -> dict:
    tok = _access_token()
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    info = requests.post(f"{API}/post/publish/creator_info/query/", headers=H, timeout=30).json()["data"]
    options = info.get("privacy_level_options", [])
    want = {"public": "PUBLIC_TO_EVERYONE", "unlisted": "SELF_ONLY", "private": "SELF_ONLY"}[cfg.get("privacy", "public")]
    privacy = want if want in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])
    size = os.path.getsize(video_path)
    caption = (meta["title"].replace("#shorts", "").strip() + " " + " ".join(meta.get("hashtags", [])))[:2200]
    init = requests.post(f"{API}/post/publish/video/init/", headers=H, timeout=30, json={
        "post_info": {"title": caption, "privacy_level": privacy, "disable_comment": False,
                      "disable_duet": False, "disable_stitch": False, "video_cover_timestamp_ms": 500,
                      "is_aigc": bool(cfg.get("label_ai_content", True))},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
    }).json()
    if init.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init failed: {init['error']}")
    pid, url = init["data"]["publish_id"], init["data"]["upload_url"]
    with open(video_path, "rb") as fh:
        put = requests.put(url, data=fh.read(), timeout=300, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}"})
    put.raise_for_status()
    status = "PROCESSING"
    for _ in range(30):
        time.sleep(10)
        s = requests.post(f"{API}/post/publish/status/fetch/", headers=H, json={"publish_id": pid}, timeout=30).json()
        status = s.get("data", {}).get("status", status)
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            break
    if status == "FAILED":
        raise RuntimeError(f"TikTok publish failed: {s}")
    return {"platform": "tiktok", "id": pid, "privacy": privacy, "status": status}
