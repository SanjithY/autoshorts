# Daily script writer guide

The poster (GitHub Actions, every 3 hours) takes the oldest file in `queue/` whose
`post_after` time has passed, renders it and uploads it. Your job each day is to keep
`queue/` stocked with **8 great, accurate scripts** for the next 24 hours.

## 1. Pick topics

- **Posting is now 3 a day** at random times in three windows (late morning, late afternoon, evening).
  Write fewer, stronger scripts: quality over volume.
- **Vary every description.** Don't reuse one template ("X happened. Sources: A, B, C."). Mix styles: a
  one-line teaser, a question, a fun extra fact, then sources in different wording ("Info from...",
  "Read more: ..."). Vary title shapes and hashtag sets too, so uploads don't look mass-produced.
- **Ease off GTA gradually**: for the next few days include about 1 GTA/gaming script per day between the
  stories and other topics, so the audience that found the channel through GTA keeps getting videos.
- **The GTA 6 run is over** (owner's call, Nov 23). Build a diverse portfolio: no more than
  1 of 8 scripts per day about GTA, and never two videos on the same topic back to back.
  Spread across: true stories, trending pop culture, streamers, gaming news, sports moments,
  science, tech, records and money.
- **Every `stickman` video is a truly interesting true story**: strange history, unbelievable
  survivals, legendary cons, record breakers, absurd sports moments, weird science. Pick stories
  most people haven't heard, with a twist you can say in the first line ("Australia went to war
  with emus. And lost."). Verify every detail with 2+ sources; if sources disagree, use the
  cautious version ("some accounts say..."). Avoid gore, suicide, sexual content, and stories whose
  main point is someone dying.
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

2-3 `stickman` true stories per day, then a mix of `stat_shock`, `top_list`, `versus`, `quiz`,
`myth_or_fact` and `news_flash`. Never the same format back to back.
Only queue a `top5_streamer` when `config.yaml → twitch_clips.streamers` has someone with
`permission: true` (the poster builds that video itself from Twitch; set `streamer` to their login).

### Gameplay footage (GTA 6)

`footage/gta6/catalog.json` lists the channel owner's own GTA 6 clips (Champs Network gameplay),
each with its length and what happens in it. Every graphic-format GTA video (stat, list, versus,
quiz, myth, news) automatically gets matching clips as its background. Add `"bg_hint"` to a scene to steer it.

**`footage_story` is paused** now that GTA isn't the focus (the owner may re-enable it). When asked for one, it is a video *about* one clip. Set
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

Stickman videos show no topic pill on screen (only the progress bar and captions), so put a big
`title` on the first scene. Use 5-7 scenes per stickman video; every scene should have visible action (no static talking heads
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

- **setting:** `city_night` (neon, palms), `city_day`, `beach`, `room`, `stage` (dance floor + disco ball), `news_desk`, `gaming`, `void`,
  and story sets: `town` (old European square), `field` (farmland), `ocean` (ship deck at night, liner on the horizon),
  `paris` (Eiffel Tower), `forest` (storm, lookout tower), `stadium` (crowd + track).
  The disco look (glowing figures, light beams, sparkles, colour grade, light-up floor indoors) is automatic.
- **action:** `idle`, `talk`, `explain`, `walk`, `run`, `sneak`, `jump`, `celebrate`, `dance`, `wave`, `point`,
  `shrug`, `facepalm`, `think`, `shocked`, `sad`, `angry`, `fall`, `sit`, `phone`, `count_money`, `flex`, `bow`.
  Use `walk`, `run` or `sneak` with `"to"` to move them (x is 0-1 across the screen). Leave `x` out to continue from the last scene.
- **face:** `neutral`, `happy`, `smug`, `sad`, `angry`, `shock`. Mouths animate for the `speaker`.
- **hat:** `cap`, `tophat`, `police`, `crown`, `headset`, `sunglasses`. **prop:** `phone`, `money`, `controller`, `trophy`, `mic`.
- **stars:** 1-6 wanted stars over the head.
- **props (world):** `car`, `sports_car`, `police_car` (x, move_to, move_time, color, driver),
  `sign` (text, color), `tv` (text, color), `chart` (values[], labels[]), `money_rain`, `palm`, `building`,
  `emu` (one bird; x, move_to, facing, scale), `flock` (n birds), `ship`, `eiffel`, `disco_ball` (x, y, r).
- **fx:** `police_lights`, `speed_lines`, `impact`, `sweat`, `hearts`, `exclaim`, `vignette`, `lightning` (bolt hits the last actor), `rain`, `confetti`. **camera:** `zoom_in`, `zoom_out`, `punch`, `pan`, `shake`.
- **Characters (skit style):** each actor can set `"outfit"` (`shirt`, `hoodie`, `vest`, `suit`, `dress`, `uniform`),
  `"hair"` (`short`, `long`, `bun`, `spiky`, `pigtails`, `curly`, or `""` for bald) and `"hair_color"` ("#3c2818").
  Unset ones are picked per character id. Hats `glasses`/`sunglasses` draw over the eyes.
- **Action timelines:** instead of one `action`, give `"do": [{"at": 0, "action": "walk", "to": 0.4},
  {"at": 1.3, "action": "point", "face": "smug"}, {"at": 2.5, "action": "laugh", "icon": "money"}]`. Write 2-4 steps per
  actor per scene so something changes every 1-2 seconds. Extra actions: `dance2`, `dance3`, `nod`, `look`, `laugh`,
  `cry`, `climb`, `throw`, `kneel`, `lie`.
- **Pop-up icons** appear by the head on a step's `"icon"` (or automatically from faces/actions): `?`, `!`, `anger`, `sweat`,
  `heart`, `money`, `idea`, `music`, `zzz`, `fire`, `skull`. Scene-level: `"pops": [{"at": 1.2, "actor": "a", "icon": "idea"}]`.
- **Camera:** the engine cuts like a skit (wide, two-shot, medium, close-up on the speaker, reaction close-ups) every
  1.5-2.3 s and blurs the background on close shots. Set `"speaker"` on every scene so close-ups land on the right person.
  Override with `"shots": [{"at": 0, "shot": "wide"}, {"at": 1.5, "shot": "close", "on": "a"}]` or `"camera": "wide"`.
- Props can enter mid-scene with `"at"` (seconds), e.g. a police car arriving at 1.4 s. Lightning can strike mid-scene: `"lightning@1.5"`.
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


## Optional: "lit set" stickman style (`"style": "lit"` on a stickman script)
Flat 2D stickmen (white heads, black line limbs, one flat clothing colour each) inside rich, lit, painted-3D sets:
perspective floors, furniture with light/dark/top faces, cast shadows, warm key light vs. cool purple shadow, haze,
a blurred foreground object, vignette, a camera that keeps moving and whip-slides between scenes, 1-2 word captions.
Pick sets, palette and light to fit the topic. Full field list: top of `pipeline/render/lit_stage.py`.
- 9-12 scenes, ONE short sentence each, at least 6 different places; every scene acts out what the sentence says.
- `place`: exterior (`light`: golden/sunset/day/night/storm/dust, `ground`, `ground_style`: wheat/furrows/road/cobbles,
  `items` with x and depth z 0-1) or interior (`light`: warm/cold/night, `wall`, `floor`: planks/tiles, `carpet`,
  `ceiling_lamps`, `items` along the back wall). Use 4-8 items per scene. Items: desk, typewriter, lamp, bookshelf,
  cabinet, filing_cabinet, counter, chair, window, curtains, map_board, flag, clock, plant, crate, paper_stacks,
  chandelier, radio, telephone, farmhouse, windmill, water_tank, gum_tree, tree, fence, broken_fence, tent, haystack,
  dam, army_truck, telegraph_pole, rock, lamp_post, awning_shop.
- Characters: `look` = {hat: top/bowler/slouch/straw/cap/helmet/kepi, hat_color, outfit: jacket/waistcoat/shirt/uniform/
  dress/overalls/coat/apron, color, moustache, glasses, brows: bushy, bowtie: "#f2c230", hair, height}. Keep each
  character's look identical in every scene. `z` puts them deeper in the set. Steps in `do` as usual.
- `crowd`: {n, kind: soldiers/farmers/townsfolk/officials, z: [near, far], action: cheer/laugh/look/shock/work}.
- Props: emu, flock (n, spread, scatter), lewis_gun (firing, fire_at, stop_at), truck, tally (text), sign, dust, or any item.
- `fg` soft foreground object: wheat, fence_post, plant, curtain, lamp, leaves. `key`: yellow caption words.
  `punch`: words that get a camera punch-in. `sfx`: [{"on": word, "sound": ...}] with sounds gunburst, clank, rumble,
  crunch, crash, paper, typewriter, engine, splash, drum, laugh, cash, thud, whistle, wind, bell, boom, whoosh, pop, ding.
