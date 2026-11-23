"""One posting cycle: research -> pick format -> write -> render -> publish -> remember.

    python run.py                 # normal run (what the schedule calls)
    python run.py --dry-run       # render only, no uploads
    python run.py --format quiz   # force a format
    python run.py --script samples/01_stat_shock.json   # render/publish a hand-written script
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
import traceback
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "history.json"
OUT = ROOT / "out"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"posts": [], "used_urls": [], "used_clip_ids": [], "used_ideas": []}


def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    st["posts"] = st["posts"][-300:]
    st["used_urls"] = st["used_urls"][-1000:]
    STATE.write_text(json.dumps(st, indent=1))


def load_ideas(st):
    p = ROOT / "ideas.md"
    if not p.exists():
        return []
    ideas = [l[2:].strip() for l in p.read_text().splitlines() if l.startswith("- ") and len(l) > 4]
    return [i for i in ideas if i not in st["used_ideas"]]


def pick_format(cfg, st, available):
    weights = {f: w for f, w in cfg["formats"].items() if f in available and w > 0}
    recent = [p["format"] for p in st["posts"][-2:]]
    pool = {f: w for f, w in weights.items() if f not in recent} or \
        {f: w for f, w in weights.items() if not recent or f != recent[-1]} or weights
    return random.choices(list(pool), weights=list(pool.values()))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--format")
    ap.add_argument("--script")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    dry = args.dry_run or cfg.get("dry_run", False)
    st = load_state()
    OUT.mkdir(exist_ok=True)
    seed = int(time.time()) % 100000
    random.seed(seed)
    stamp = time.strftime("%Y%m%d-%H%M")

    from pipeline import clips, research, writer
    from pipeline.render.scenes import render_animated

    available = set(cfg["formats"]) - {"clip_react", "gameplay_story"}
    if clips.allowed_streamers(cfg):
        available.add("clip_react")
    footage, fstart = clips.pick_footage(cfg)
    if footage:
        available.add("gameplay_story")
    fmt = args.format or pick_format(cfg, st, available)
    if args.script:
        fmt = json.loads(Path(args.script).read_text()).get("format", fmt)
    print(f"[run] format = {fmt}")

    video = str(OUT / f"{stamp}-{fmt}.mp4")
    meta = {}
    if args.script:
        meta = json.loads(Path(args.script).read_text())
        render_animated(meta, video, cfg, seed=seed)
    elif fmt == "clip_react":
        clip = clips.find_clip(cfg, set(st["used_clip_ids"]))
        if not clip:
            print("[run] no new allowed clip found; falling back to an animated format")
            available.discard("clip_react")
            fmt = pick_format(cfg, st, available)
        else:
            src = clips.download_clip(clip, tempfile.mkdtemp())
            words = clips.transcribe_words(src)
            pkg = writer.write_clip_package(clip, " ".join(w["w"] for w in words), cfg)
            credit = f"Clip: twitch.tv/{clip['broadcaster_name']}"
            clips.render_clip(src, pkg["hook"], credit, video, words)
            meta = {**pkg, "format": fmt, "clip_id": clip["id"],
                    "description": pkg.get("description", "") + f"\n\nClip by {clip['broadcaster_name']}: {clip['url']}"}
            st["used_clip_ids"].append(clip["id"])
    if not meta:
        res = research.gather(cfg["news_queries"], set(st["used_urls"]))
        ideas = load_ideas(st)
        from pipeline import fallback
        try:
            meta = writer.write_script(fmt, res, ideas, [p["title"] for p in st["posts"]], cfg)
        except RuntimeError as ex:
            print(f"[run] AI script failed ({ex}); using a no-AI fallback")
            meta = fallback.news_from_headline(res, cfg, set(st["used_urls"]))
            if not meta:
                meta = fallback.pick_bank(st.setdefault("used_bank", []))
                st["used_bank"].append(meta["bank_id"])
            fmt = meta["format"]
        bg = footage if fmt == "gameplay_story" else None
        render_animated(meta, video, cfg, background_video=bg, bg_start=fstart, seed=seed)
        st["used_urls"] += meta.get("source_urls", [])
        if meta.get("used_idea"):
            st["used_ideas"].append(meta["used_idea"])
    (OUT / f"{stamp}-{fmt}.json").write_text(json.dumps(meta, indent=1))
    print(f"[run] rendered {video}: {meta.get('title')}")
    for sc in meta.get("scenes", []):
        print(f"[script] {sc.get('type'):9} | {sc.get('text') or sc.get('question') or sc.get('label') or ''} | {sc.get('say')}")

    results = []
    if not dry:
        from pipeline.publish import instagram, tiktok, youtube
        uploaders = {"youtube": youtube.upload, "tiktok": tiktok.upload, "instagram": instagram.upload}
        for name, on in cfg.get("platforms", {}).items():
            if not on:
                continue
            try:
                r = uploaders[name](video, meta, cfg)
                print(f"[run] {name}: {r}")
                results.append(r)
            except Exception as ex:  # one platform failing never blocks the others
                traceback.print_exc()
                results.append({"platform": name, "error": str(ex)[:300]})
    st["posts"].append({"time": stamp, "format": fmt, "title": meta.get("title", ""), "results": results})
    save_state(st)
    if results and all("error" in r for r in results):
        sys.exit(1)  # makes the GitHub Actions run show red so you notice


if __name__ == "__main__":
    main()
