# Daily script writer guide

The poster (GitHub Actions, every 3 hours) takes the oldest file in `queue/` whose
`post_after` time has passed, renders it and uploads it. Your job each day is to keep
`queue/` stocked with **8 great, accurate scripts** for the next 24 hours.

## 1. Pick topics

- Read `config.yaml → focus`. While today is on or before `focus.until`, about
  `focus.share` of the scripts (6 of 8) are about the focus topic (GTA 6), and the rest are trending.
  After that date, all 8 come from trends + evergreen fun topics.
- Read `state/trends.json` (Google Trends + YouTube trending, already filtered) and
  search the web yourself for what's blowing up **today** with the YouTube Shorts audience:
  gaming, streamers, viral moments, movies/TV/music, sports highlights, tech/gadgets,
  science and "fun fact" stories, money/records.
- **Skip:** politics, elections, wars, crime, deaths, disasters, tragedies, health scares,
  anything sexual, and rumors about private people. Keep it fun, broad, and safe.
- Read `state/history.json` and `queue/done/` so you don't repeat a topic or angle from the last 7 days.

## 2. Research every fact

Use web search for every claim, number, date and name. Put the sources in `description`
("Sources: Variety, IGN"). Label estimates and rumors as such. Never invent numbers,
quotes or stats ("90% of people..."). No story spoilers for games or movies.
Stickman skits may show generic characters; don't depict a real person doing or saying
something they didn't do.

## 3. Vary the formats (per day)

At least 2 `stickman`, about 1 in 5 `footage_story` (while GTA 6 is the focus), then a mix of `stat_shock`, `top_list`, `versus`, `quiz`,
`myth_or_fact` and `news_flash`. Never the same format back to back.
Only queue a `top5_streamer` when `config.yaml → twitch_clips.streamers` has someone with
`permission: true` (the poster builds that video itself from Twitch; set `streamer` to their login).

### Gameplay footage (GTA 6)

`footage/gta6/catalog.json` lists the channel owner's own GTA 6 clips (Champs Network gameplay),
each with its length and what happens in it. Every graphic-format GTA video (stat, list, versus,
quiz, myth, news) automatically gets matching clips as its background. Add `"bg_hint"` to a scene to steer it.

**About 1 in 5 videos should be a `footage_story`:** a video *about* one clip. Set
`"format": "footage_story"`, `"footage": "gta6/<file>.mp4"` (from the catalog), and
`"footage_audio": 0.35` (game sound under the narration). Narrate what happens in the clip in first person ("I"),
like a funny gamer recap, using the hook, text, stars and outro scene types. Keep the narration within about the clip's
length; a short clip loops. Don't reuse a clip that had its own footage_story in the last 7 days, and
keep it light (no glorifying violence against people; focus on chases, crashes, cops and funny moments).
Credit "(Champs Network)" in the description.

## 4. Retention rules

- First second = hook: 2-6 word on-screen text plus a spoken line under 12 words.
- Something changes every 2-4 seconds. Each scene is 1-2 short sentences.
- 55-110 spoken words total (20-40 s). End with a question viewers answer in the comments,
  or a line that loops back to the start.
- Title under 70 characters, curiosity-driven, ends with `#shorts`.

## 5. File format

One JSON file per video: `queue/YYYYMMDD-HHMM-<slug>.json`. Set `post_after`
(UTC, `YYYY-MM-DDTHH:MM`) and space the 8 files 3 hours apart, starting with the next run.

```json
{
  "format": "stickman",
  "post_after": "2026-11-24T03:00",
  "kicker": "GTA 6 · explained",
  "title": "GTA 6 cops remember your OUTFIT #gta6 #shorts",
  "description": "One or two sentences. Sources: GamesRadar, Beebom.",
  "hashtags": ["#gta6", "#shorts"],
  "theme": "gaming",
  "topic_key": "gta6",
  "stock_query": "police car night",
  "scenes": [ ... ]
}
```

- `theme` picks the animated backdrop when there's no footage: `gaming`, `news` (VHS news tape + breaking banner),
  `sports`, `tech`, `space`, `money`, `entertainment`.
- `topic_key` matches a footage folder (`footage/gta6/`). Clips are matched to each scene by file name,
  so add `"bg_hint": "police chase"` to a scene to steer it.
- `stock_query` (optional) is used for free Pexels stock video on non-gaming topics, when the
  PEXELS_API_KEY secret exists.

### Scene types for the graphic formats

| type | fields |
|---|---|
| hook | text, highlight[], say |
| text | text (≤8 words), highlight[], sub (optional), say |
| stat | value (number), prefix, suffix, decimals, label (≤4 words), sub, say |
| bars | title, items[{label, value, display}] (2-4), highlight (index), say |
| versus | left, right, rows[{label, l, r}] (2-4), say |
| list_item | n, text (≤5 words), highlight[], say |
| stars | n (1-6), text, highlight[], say |
| quiz_q / quiz_a | question, options[2-3], answer (index), say |
| outro | text (≤6 words), cta (≤3 words), highlight[], say |

`say` is exactly what the narrator speaks: write numbers the way they're said
("three point seven nine billion"). Write "GTA 6", never "G T A".

### Stickman scenes (`"type": "stick"`)

Use 4-7 of these per stickman video; every scene should have visible action (no static talking heads
back to back).

```json
{"type": "stick", "setting": "city_night", "speaker": "a", "say": "...",
 "title": "OPTIONAL BIG TEXT AT TOP",
 "actors": [{"id": "a", "x": 0.3, "action": "run", "to": 0.8, "face": "shock", "hat": "cap",
             "color": "#ff2e63", "prop": "phone", "stars": 5, "facing": 1, "then": "idle"}],
 "props": [{"kind": "police_car", "x": -0.3, "move_to": 0.5, "move_time": 2}],
 "bubble": {"actor": "a", "text": "SHORT LINE", "thought": false},
 "fx": ["police_lights", "speed_lines"], "camera": "zoom_in"}
```

- **setting:** `city_night` (neon, palms), `city_day`, `beach`, `room`, `stage`, `news_desk`, `gaming`, `void`
- **action:** `idle`, `talk`, `explain`, `walk`, `run`, `sneak`, `jump`, `celebrate`, `dance`, `wave`, `point`,
  `shrug`, `facepalm`, `think`, `shocked`, `sad`, `angry`, `fall`, `sit`, `phone`, `count_money`, `flex`, `bow`.
  Use `walk`, `run` or `sneak` with `"to"` to move them (x is 0-1 across the screen). Leave `x` out to continue from the last scene.
- **face:** `neutral`, `happy`, `smug`, `sad`, `angry`, `shock`. Mouths animate for the `speaker`.
- **hat:** `cap`, `tophat`, `police`, `crown`, `headset`, `sunglasses`. **prop:** `phone`, `money`, `controller`, `trophy`, `mic`.
- **stars:** 1-6 wanted stars over the head.
- **props (world):** `car`, `sports_car`, `police_car` (x, move_to, move_time, color, driver),
  `sign` (text, color), `tv` (text, color), `chart` (values[], labels[]), `money_rain`, `palm`, `building`.
- **fx:** `police_lights`, `speed_lines`, `impact`, `sweat`, `hearts`, `exclaim`, `vignette`. **camera:** `zoom_in`, `zoom_out`, `punch`, `pan`, `shake`.
- Keep bubbles short (2-6 words) and put them on the speaking actor. Give recurring characters
  the same id, hat and color across scenes.

## 6. Check, then push

```bash
python - <<'PY'
import json, glob
from pipeline import writer
for f in sorted(glob.glob("queue/*.json")):
    writer.validate(json.load(open(f))); print("ok", f)
PY
python run.py --dry-run --script queue/<one stickman file>.json   # render one to be sure it works
git add queue && git commit -m "queue: scripts for <date>" && git push
```
