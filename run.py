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


PREFER = None   # a fixed-time queue file chosen by the scheduler for this run


def next_queued():
    """The scheduler's fixed-time pick, else the oldest queued script whose post_after time has passed.
    Files with an exact "post_at" time are only ever posted by the scheduler at that time."""
    q = ROOT / "queue"
    if not q.exists():
        return None
    if PREFER and PREFER.exists():
        return PREFER, json.loads(PREFER.read_text())
    now = time.strftime("%Y-%m-%dT%H:%M", time.gmtime())
    for p in sorted(q.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if d.get("post_at") and d["post_at"] > now:
            continue
        if d.get("post_after", "") <= now:
            return p, d
    return None


def _utc(s):
    import datetime as dt
    return dt.datetime.strptime(s.rstrip("Z")[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc)


def schedule_gate(cfg, st):
    """Decide whether this run should post, and when. Returns seconds to wait, or None to skip.

    - Queue files with "post_at" go out at exactly that time.
    - Otherwise the day has a few posting windows (local time); each window gets one post at a random
      time inside it, chosen fresh every day. Runs fire hourly, so a run posts if its window's time falls
      within the next ~65 minutes (it waits until then) and that window hasn't posted yet.
    - Nothing regular posts before "pause_until".
    """
    import datetime as dt
    from zoneinfo import ZoneInfo
    sch = cfg.get("schedule")
    if not sch:
        return 0
    global PREFER
    now = dt.datetime.now(dt.timezone.utc)
    ahead = dt.timedelta(minutes=int(sch.get("lookahead_min", 65)))
    late = dt.timedelta(minutes=40)
    posted = [dt.datetime.strptime(p["time"], "%Y%m%d-%H%M").replace(tzinfo=dt.timezone.utc)
              for p in st["posts"] if any("id" in r for r in p.get("results", []))]
    # 1) fixed-time posts
    for p in sorted((ROOT / "queue").glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if d.get("post_at"):
            t = _utc(d["post_at"])
            if now - late <= t <= now + ahead:
                PREFER = p
                return max(0.0, (t - now).total_seconds())
    fixed = []
    for p in (ROOT / "queue").glob("*.json"):
        try:
            if json.loads(p.read_text()).get("post_at"):
                fixed.append(_utc(json.loads(p.read_text())["post_at"]))
        except Exception:
            pass
    # 2) paused?
    if sch.get("pause_until") and now < _utc(sch["pause_until"]):
        print(f"[run] uploads paused until {sch['pause_until']} UTC")
        return None
    # 3) random time inside each daily window
    tz = ZoneInfo(sch.get("timezone", "America/Chicago"))
    local = now.astimezone(tz)
    def windows_for(day):
        w = sch["windows"]
        for start_day, ww in sorted((sch.get("windows_from") or {}).items()):
            if day.isoformat() >= str(start_day):
                w = ww
        return w
    for day in (local.date() - dt.timedelta(days=1), local.date()):
        for i, (a, b) in enumerate(windows_for(day)):
            ha, ma = map(int, a.split(":"))
            hb, mb = map(int, b.split(":"))
            start = dt.datetime(day.year, day.month, day.day, ha, ma, tzinfo=tz)
            end = dt.datetime(day.year, day.month, day.day, hb, mb, tzinfo=tz)
            rnd = random.Random(f"{day.isoformat()}-{i}")
            target = start + (end - start) * rnd.random()
            if not (now - late <= target <= now + ahead):
                continue
            if any(start - dt.timedelta(minutes=30) <= t <= end + dt.timedelta(minutes=45) for t in posted + fixed):
                continue   # this window already has its post (or a fixed-time post is scheduled in it)
            print(f"[run] window {a}-{b}: today's post time is {target.astimezone(tz):%H:%M} local")
            return max(0.0, (target - now).total_seconds())
    print("[run] not a posting time")
    return None


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
    ap.add_argument("--force", action="store_true", help="post even if the last post was recent")
    ap.add_argument("--prebuilt", help="folder with an already-rendered .mp4 + .json (e.g. a past run's artifact) to upload as-is")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    dry = args.dry_run or cfg.get("dry_run", False)
    st = load_state()
    OUT.mkdir(exist_ok=True)
    if not dry and not args.force and not args.prebuilt and not args.script and not args.format:
        wait = schedule_gate(cfg, st)
        if wait is None:
            return
        if wait > 0:
            print(f"[run] waiting {wait / 60:.0f} min for the scheduled time")
            time.sleep(wait)
    # Several timers can fire: never post twice too close together (fixed-time posts are exempt).
    if not dry and not args.force and PREFER is None:
        last = [p for p in st["posts"] if any("id" in r for r in p.get("results", []))]
        if last:
            import datetime as _dt
            t_last = _dt.datetime.strptime(last[-1]["time"], "%Y%m%d-%H%M")
            mins = (_dt.datetime.utcnow() - t_last).total_seconds() / 60
            if mins < cfg.get("min_gap_minutes", 60):
                print(f"[run] last post was {mins:.0f} min ago; skipping this run (another timer already posted)")
                return
    seed = int(time.time()) % 100000
    random.seed(seed)
    stamp = time.strftime("%Y%m%d-%H%M", time.gmtime())

    if args.prebuilt:
        pre = Path(args.prebuilt)
        vids = sorted(pre.rglob("*.mp4"))
        if not vids:
            sys.exit(f"[run] no .mp4 found in {pre}")
        video = str(vids[0])
        meta = json.loads(vids[0].with_suffix(".json").read_text())
        fmt = meta.get("format", "prebuilt")
        print(f"[run] uploading prebuilt video {vids[0].name}: {meta.get('title')}")
        st["used_clip_ids"] += [c for c in meta.get("clip_ids", []) if c not in st["used_clip_ids"]]
        return _publish(cfg, dry, st, stamp, fmt, video, meta)

    from pipeline import clips, research, writer
    from pipeline.render.scenes import render_animated
    from pipeline import trends as trends_mod
    try:
        trends_mod.refresh()
    except Exception as ex:
        print(f"[run] trends refresh failed: {ex}")

    available = set(cfg["formats"]) - {"clip_react", "gameplay_story", "top5_streamer"}
    if clips.allowed_streamers(cfg):
        available |= {"clip_react", "top5_streamer"}
    footage, fstart = clips.pick_footage(cfg)
    if footage:
        available.add("gameplay_story")
    fmt = args.format or pick_format(cfg, st, available)
    if args.script:
        fmt = json.loads(Path(args.script).read_text()).get("format", fmt)
    print(f"[run] format = {fmt}")

    video = str(OUT / f"{stamp}-{fmt}.mp4")
    meta = {}
    queued = None if args.script or args.format else next_queued()
    if queued:
        qpath, meta = queued
        fmt = meta.get("format", "queued")
        video = str(OUT / f"{stamp}-{fmt}.mp4")
        print(f"[run] using queued script {qpath.name}: {meta.get('title')}")
        try:
            if meta.get("prebuilt_asset"):  # an exact, already-approved video stored in prebuilt/
                video = str(ROOT / "prebuilt" / meta["prebuilt_asset"])
                if not Path(video).exists():
                    raise RuntimeError(f"prebuilt video {video} missing")
                print(f"[run] using prebuilt video {meta['prebuilt_asset']} as-is (no re-render)")
            elif meta.get("format") == "top5_streamer":
                from pipeline import compilation
                m = compilation.build(cfg, video, st, prefer=meta.get("streamer"))
                if not m:
                    raise RuntimeError("no allowed streamer clips available")
                meta = {**meta, **m}
                st["used_clip_ids"] += m.get("clip_ids", [])
            else:
                meta = writer.validate(meta)
                render_animated(meta, video, cfg, seed=seed)
            if not dry:  # test runs leave the queue untouched
                done = ROOT / "queue" / "done"
                done.mkdir(parents=True, exist_ok=True)
                qpath.rename(done / qpath.name)
        except Exception as ex:
            print(f"[run] queued script failed ({ex}); moving it to queue/failed and continuing")
            if not dry:
                bad = ROOT / "queue" / "failed"
                bad.mkdir(parents=True, exist_ok=True)
                qpath.rename(bad / qpath.name)
            meta = {}
    if meta:
        pass
    elif fmt == "top5_streamer":
        from pipeline import compilation
        m = compilation.build(cfg, video, st)
        if m:
            meta = m
            st["used_clip_ids"] += m.get("clip_ids", [])
        else:
            fmt = "stat_shock"
    if meta:
        pass
    elif args.script:
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
            from pipeline.render.moments import render_moment
            render_moment(src, video, title=pkg.get("hook") or clip["title"], streamer=clip["broadcaster_name"],
                          credit=f"twitch.tv/{clip['broadcaster_name']}", rank=None, words=words)
            meta = {**pkg, "format": fmt, "clip_id": clip["id"],
                    "description": pkg.get("description", "") + f"\n\nClip by {clip['broadcaster_name']}: {clip['url']}"}
            st["used_clip_ids"].append(clip["id"])
    if not meta:
        res = research.gather(cfg["news_queries"], set(st["used_urls"]))
        ideas = load_ideas(st)
        from pipeline import fallback
        import os
        has_ai = any(os.environ.get(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY")) or \
            ("ollama" in cfg.get("llm", {}).get("providers", []) and os.environ.get("OLLAMA_HOST"))
        meta = None
        if has_ai:
            try:
                meta = writer.write_script(fmt, res, ideas, [p["title"] for p in st["posts"]], cfg)
            except RuntimeError as ex:
                print(f"[run] AI script failed ({ex}); using a no-AI fallback")
        if not meta:
            # no AI: alternate between today's headline and a fact-checked bank script
            want_news = fmt == "news_flash" or random.random() < 0.5
            meta = fallback.news_from_headline(res, cfg, set(st["used_urls"])) if want_news else None
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

    return _publish(cfg, dry, st, stamp, fmt, video, meta)


def _publish(cfg, dry, st, stamp, fmt, video, meta):
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
    if dry:  # test renders never touch history (they used to mark clips as used)
        return
    st["posts"].append({"time": stamp, "format": fmt, "title": meta.get("title", ""), "results": results})
    save_state(st)
    if results and all("error" in r for r in results):
        sys.exit(1)  # makes the GitHub Actions run show red so you notice


if __name__ == "__main__":
    main()
