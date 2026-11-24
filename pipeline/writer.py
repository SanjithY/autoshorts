"""Turns research + a chosen format into a scene-by-scene script the renderer understands."""
from __future__ import annotations

import json

from .llm import complete_json

SYSTEM = """You write viral YouTube Shorts / TikTok scripts for a faceless {topic} channel.
Everything you output is rendered automatically, so follow the JSON schema exactly.

RETENTION RULES (these decide whether the video gets views):
1. HOOK in the first second. Scene 1 is a "hook": on-screen text of 2-6 punchy words and a spoken line
   under 12 words that creates curiosity or shock. No greetings, no "hey guys", no channel intro.
2. Change something every 2-4 seconds: each scene is short (1-2 spoken sentences, under 25 words).
3. Open loops: tease the payoff early ("number one is wild") and pay it off at the end.
4. Talk like a hyped gamer friend: short sentences, plain words, second person ("you").
5. Total spoken words 55-110 (about 20-40 seconds).
6. End with an "outro" that asks ONE specific question viewers can answer in a comment, or that loops
   back into the first line so the video replays seamlessly.
7. Titles under 70 characters, curiosity-driven, end with #shorts. Description 1-3 sentences that names
   the sources used.

HONESTY RULES (breaking these gets the channel flagged):
- Use ONLY facts from the provided news and fact list. Never invent numbers, percentages, quotes, release
  details or "leaks". No fake stats in hooks like "90% of people...".
- Label estimates as estimates ("analysts estimate", "reportedly"). Community/Reddit posts are rumors.
- No spoilers of the story's ending or major plot twists.

SCENE TYPES (pick from these; fields shown):
- hook: text, highlight[], say
- text: text (max 8 words), highlight[], sub (optional, max 6 words), say
- stat: value (number), prefix, suffix, decimals, label (max 4 words), sub (optional), say
- bars: title, items[{label, value(number), display}] (2-4 items), highlight (index), say
- versus: left, right, rows[{label, l, r}] (2-4 rows, short values), say
- list_item: n, text (max 5 words), highlight[], say
- stars: n (1-6), text (max 5 words), highlight[], say
- quiz_q: question (max 8 words), options[2-3 short strings], answer (index), say
- quiz_a: same question/options/answer as the quiz_q before it, say (reveal + 1 fact)
- outro: text (max 6 words), cta (max 3 words), highlight[], say
"highlight" lists words from "text" to color yellow. "say" is exactly what the narrator speaks.
Write numbers in "say" the way they should be spoken (e.g. "three point seven nine billion").
"""

FORMAT_GUIDE = {
    "stat_shock": "One jaw-dropping number. hook -> stat (count-up) -> bars or text giving context/comparison -> 1-2 text -> outro.",
    "top_list": "Countdown of 3 things. hook teasing #1 -> list_item 3 -> list_item 2 -> list_item 1 (best) -> outro.",
    "versus": "Head-to-head comparison (e.g. GTA V vs GTA VI, editions, platforms). hook -> versus (3-4 rows) -> text or stars -> outro asking which side wins.",
    "quiz": "Trivia game. hook -> quiz_q -> quiz_a -> quiz_q -> quiz_a -> outro asking for their score.",
    "myth_or_fact": "TRUE or FALSE game about claims people believe. hook -> quiz_q with options ['TRUE','FALSE'] -> quiz_a -> repeat once -> outro.",
    "news_flash": "Today's single biggest headline. hook -> text (what happened) -> stat or text (key detail) -> text (why it matters) -> outro.",
    "gameplay_story": "Narration over gameplay footage. Tip or story format: hook -> 3-4 text/list_item scenes -> outro. Keep on-screen text short.",
}


EXAMPLE_FOR = {"stat_shock": "example_stat", "news_flash": "example_stat", "versus": "example_versus",
               "quiz": "example_quiz", "myth_or_fact": "example_quiz", "top_list": "example_list",
               "gameplay_story": "example_list"}


def _example(fmt):
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "samples" / "examples" / f"{EXAMPLE_FOR.get(fmt, 'example_stat')}.json"
    return p.read_text() if p.exists() else ""


def build_prompt(fmt, research, ideas, history_titles, topic):
    news = [{k: v for k, v in it.items() if k in ("title", "summary", "source", "published", "body")}
            for it in research["news"][:10]]
    return f"""FORMAT: {fmt} - {FORMAT_GUIDE[fmt]}

CREATOR IDEAS (use one if it fits this format, otherwise ignore):
{json.dumps(ideas[:10], indent=1)}

RECENT VIDEO TITLES (do NOT repeat these angles):
{json.dumps(history_titles[-30:], indent=1)}

VERIFIED FACTS:
{json.dumps(research['facts'], indent=1)}

LATEST NEWS ABOUT {topic}:
{json.dumps(news, indent=1)[:5000]}

EXAMPLE OF THE JSON STRUCTURE. It is about a DIFFERENT game on purpose: copy only the key names and
scene types. Every fact, number and word in YOUR video must come from the {topic} facts/news above:
{_example(fmt)}

Return JSON: {{"format": "{fmt}", "kicker": "<{topic} label, max 4 words>", "title": "...",
"description": "...", "hashtags": ["#..."], "used_idea": "<idea text or empty>",
"source_urls": ["<urls of news you used>"], "scenes": [ ... ]}}"""


REQUIRED = {"stick": ["say"], "hook": ["text", "say"], "text": ["text", "say"], "stat": ["value", "label", "say"],
            "bars": ["items", "say"], "versus": ["rows", "say"], "list_item": ["n", "text", "say"],
            "stars": ["n", "text", "say"], "quiz_q": ["question", "options", "answer", "say"],
            "quiz_a": ["question", "options", "answer", "say"], "outro": ["text", "say"]}


TYPE_ALIASES = {"intro": "hook", "opening": "hook", "cta": "outro", "ending": "outro", "end": "outro",
                "fact": "text", "point": "text", "statement": "text", "headline": "text", "news": "text",
                "number": "stat", "statistic": "stat", "comparison": "versus", "list": "list_item",
                "item": "list_item", "question": "quiz_q", "answer": "quiz_a", "chart": "bars"}
SAY_KEYS = ("say", "narration", "voiceover", "voice_over", "voice", "script", "speech", "line", "spoken")
TEXT_KEYS = ("text", "on_screen_text", "onscreen_text", "screen_text", "caption", "title", "headline")


def normalize(script: dict) -> dict:
    """Repair the usual ways small models drift from the schema."""
    if not isinstance(script, dict):
        raise ValueError("not an object")
    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        scenes = next((v for v in script.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
    out = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        t = str(sc.get("type") or sc.get("scene_type") or sc.get("kind") or "text").lower().strip()
        t = TYPE_ALIASES.get(t, t)
        if t not in REQUIRED:
            t = "text"
        sc["type"] = t
        if not sc.get("say"):
            sc["say"] = next((str(sc[k]) for k in SAY_KEYS if sc.get(k)), "")
        if not sc.get("text") and t in ("hook", "text", "list_item", "stars", "outro"):  # stick scenes use "title"
            sc["text"] = next((str(sc[k]) for k in TEXT_KEYS if sc.get(k)), "")
            if not sc["text"] and sc["say"]:
                sc["text"] = " ".join(sc["say"].split()[:6])
        if t == "stat":
            try:
                sc["value"] = float(str(sc.get("value", "")).replace(",", "").replace("$", "").strip("xX%"))
                sc.setdefault("label", sc.get("text", ""))
            except ValueError:  # not a usable number -> show as plain text instead
                sc["type"] = "text"
                sc["text"] = sc.get("text") or sc.get("label") or " ".join(sc["say"].split()[:6])
        if t == "list_item":
            sc.setdefault("n", len([x for x in out if x["type"] == "list_item"]) + 1)
        if t == "stars":
            sc["n"] = int(float(sc.get("n", 6) or 6))
        for k in ("highlight",):
            if k in sc and not isinstance(sc[k], list):
                sc[k] = [str(sc[k])]
        if sc["say"]:
            out.append(sc)
    if out and out[0]["type"] not in ("hook", "stick"):
        first = out[0]
        out[0] = {"type": "hook", "say": first["say"],
                  "text": first.get("text") or " ".join(first["say"].split()[:5])}
    if out and out[-1]["type"] not in ("outro", "stick"):
        out.append({"type": "outro", "text": "What do you think?", "cta": "Comment below",
                    "say": "What do you think? Tell me in the comments."})
    script["scenes"] = out
    if not script.get("title"):
        script["title"] = (out[0].get("text", "GTA 6") if out else "GTA 6") + " #shorts"
    return script


def validate(script: dict):
    script = normalize(script)
    sc = script.get("scenes") or []
    mx = 12 if script.get("style") == "lit" else 9
    assert 3 <= len(sc) <= mx, f"need 3-{mx} scenes"
    assert sc[0]["type"] in ("hook", "stick"), "first scene must be a hook (or a stickman scene)"
    words = 0
    for s in sc:
        assert s.get("type") in REQUIRED, f"bad type {s.get('type')}"
        for k in REQUIRED[s["type"]]:
            assert k in s, f"{s['type']} missing {k}"
        words += len(s["say"].split())
        if s["type"] == "stat":
            s["value"] = float(str(s["value"]).replace(",", ""))
        if s["type"] == "bars":
            for it in s["items"]:
                it["value"] = float(str(it["value"]).replace(",", ""))
        if s["type"] in ("quiz_q", "quiz_a"):
            s["answer"] = int(s["answer"])
            assert 0 <= s["answer"] < len(s["options"])
    assert 35 <= words <= 140, f"spoken words {words} out of range"
    if script.get("footage"):
        from pathlib import Path
        assert (Path(__file__).resolve().parents[1] / "footage" / script["footage"]).exists(), \
            f"footage {script['footage']} not found in footage/"
    assert script.get("title")
    return script


def _numbers_in(text):
    import re
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def fact_check(script, research):
    """Every number shown on screen must appear somewhere in the facts/news we gave the model."""
    corpus = json.dumps(research, ensure_ascii=False)
    known = _numbers_in(corpus)
    kn = sorted({float(k) for k in known if k.replace(".", "", 1).isdigit()} - {0.0})

    def num_ok(n):
        if n in known or n.rstrip("0").rstrip(".") in known or n in ("1", "2", "3", "4", "5", "6"):
            return True
        x = float(n)
        for k in kn:  # same number in other units (3.79 billion == 3790 million)
            if any(abs(x - k * f) <= 0.01 * max(x, 1e-9) for f in (1000, 0.001, 1e6, 1e-6)):
                return True
        if x < 100:  # a ratio like "4.6x" between two real numbers (also across billion/million)
            pool = kn + [k * 1000 for k in kn if k < 100]
            return any(abs(a / b - x) <= 0.03 * x for a in pool for b in pool if b and a > b)
        return False

    def ok(v):
        v = str(v).replace(",", "").replace("$", "")
        return all(num_ok(n) for n in _numbers_in(v))
    for sc in script["scenes"]:
        vals = []
        if sc["type"] == "stat":
            v = sc["value"]
            vals.append(str(int(v)) if float(v).is_integer() else str(v))
        if sc["type"] == "bars":
            vals += [it.get("display", it["value"]) for it in sc["items"]]
        if sc["type"] == "versus":
            vals += [r.get("l", "") for r in sc["rows"]] + [r.get("r", "") for r in sc["rows"]]
        for v in vals:
            assert ok(v), f"number {v!r} is not in the provided facts/news; use only real numbers"


def write_script(fmt, research, ideas, history_titles, cfg):
    system = SYSTEM.replace("{topic}", cfg["topic"])
    prompt = build_prompt(fmt, research, ideas, history_titles, cfg["topic"])
    last = None
    script = None
    for attempt in range(2):
        try:
            script = complete_json(prompt if not last else prompt + f"\n\nPrevious attempt was invalid: {last}. Fix it.",
                                   system, cfg.get("llm", {}))
            script = validate(script)
            fact_check(script, research)
            ex_text = _example(fmt)
            copied = [sc["say"] for sc in script["scenes"] if sc["say"] and sc["say"] in ex_text]
            assert script["title"] not in ex_text, "title copied from the example; write a new one"
            assert len(copied) <= 1, "scenes copied from the example; write new content"
            return script
        except (AssertionError, KeyError, ValueError, TypeError) as ex:
            last = str(ex)
            print(f"[writer] attempt {attempt + 1} invalid: {ex!r}")
            try:
                print("[writer] model output was:", json.dumps(script)[:800])
            except Exception:
                pass
    raise RuntimeError(f"Could not get a valid script: {last}")


CLIP_SYSTEM = """You package a streamer's clip for Shorts/TikTok. Given the clip title, streamer, and
transcript, return JSON: {"hook": "<2-6 word on-screen hook, ALL about what happens>",
"title": "<under 70 chars, curiosity, ends with #shorts>", "description": "<1-2 sentences + credit line>",
"hashtags": ["#..."]}. Never claim anything the transcript doesn't show."""


def write_clip_package(clip: dict, transcript: str, cfg):
    prompt = json.dumps({"streamer": clip["broadcaster_name"], "clip_title": clip["title"],
                         "transcript": transcript[:2000], "topic": cfg["topic"]})
    return complete_json(prompt, CLIP_SYSTEM, cfg.get("llm", {}))
