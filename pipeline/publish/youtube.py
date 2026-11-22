"""YouTube Shorts upload via the free YouTube Data API v3."""
from __future__ import annotations

import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload(video_path: str, meta: dict, cfg: dict) -> dict:
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = meta["title"]
    if "#shorts" not in title.lower():
        title = (title[:90] + " #shorts")
    tags = [h.lstrip("#") for h in meta.get("hashtags", [])][:15]
    body = {
        "snippet": {"title": title[:100], "description": meta.get("description", "") + "\n\n" +
                    " ".join(meta.get("hashtags", [])), "tags": tags, "categoryId": cfg.get("youtube_category", "20")},
        "status": {"privacyStatus": cfg.get("privacy", "public"), "selfDeclaredMadeForKids": False,
                   # only needed for *realistic* altered/synthetic media; animated graphics don't qualify
                   "containsSyntheticMedia": bool(meta.get("realistic_synthetic", False))},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True,
                                                        mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    status = resp.get("status", {})
    if cfg.get("privacy", "public") == "public" and status.get("privacyStatus") != "public":
        print("[youtube] WARNING: video came back as", status.get("privacyStatus"),
              "- your API project may need YouTube's (free) API audit. See SETUP.md.")
    return {"platform": "youtube", "id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "privacy": status.get("privacyStatus")}
