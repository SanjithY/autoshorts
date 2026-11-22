# AutoShorts: GTA 6 auto-poster (100% free)

Every 3 hours, GitHub runs this repo on its free servers and:

1. **Researches**: Bing + Google News RSS, r/GTA6, plus your `facts.yaml`
2. **Picks a format**: it never repeats the same format twice in a row. Formats: stat shock, top-3 list, versus, quiz, myth-or-fact, news flash, streamer clip, and gameplay story
3. **Writes** a script with a free LLM (GitHub Models, built into GitHub). The prompt has hook and retention rules built in, and it isn't allowed to invent facts
4. **Renders** a 1080×1920 video: animated neon-Vice-City graphics, a free local AI voice (Kokoro), word-by-word captions, music it synthesizes itself (so there are no copyright claims), and sound effects
5. **Posts** to YouTube Shorts, TikTok, and optionally Instagram Reels, then saves its history so it doesn't repeat itself

Your only job: add lines to `ideas.md` whenever you want (optional).

---

## 1. Put it on GitHub (5 min)

1. Create a free GitHub account and a **new repository**. Upload this whole folder.
   * **Public repo**: GitHub Actions minutes are free and unlimited. Your code is visible, but your keys stay hidden in Secrets.
   * **Private repo**: you get 2,000 free minutes a month. Each run takes about 4–5 min, so 8 runs a day is about 1,200 min a month. That fits.
2. Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write**.

## 2. Free API keys → GitHub Secrets

Add each of these under **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Where to get it |
|---|---|
| *(none needed for the AI writer)* | Scripts are written with free **GitHub Models** using the repo's own token. `GEMINI_API_KEY` / `GROQ_API_KEY` are optional backups. |
| `GROQ_API_KEY` *(optional backup)* | console.groq.com → API Keys (free) |
| `TOKEN_KEY` *(optional)* | run `python scripts/make_token_key.py`; if absent, a key is derived from your client secret |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | step 3 |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` | step 4 |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` *(optional)* | step 5 |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` *(optional)* | step 6 |

## 3. YouTube

1. console.cloud.google.com → new project → **APIs & Services → Library** → enable **YouTube Data API v3**.
2. **OAuth consent screen**: External, add your email as a test user, then click **Publish app / In production**.
   ⚠️ If you leave it in "Testing", your login expires every 7 days and uploads stop.
   You'll see an "unverified app" warning when you log in. That's fine, because it's your own app.
3. **Credentials → Create OAuth client → Desktop app**. Download the JSON as `scripts/client_secret.json`.
4. On your computer, run `pip install google-auth-oauthlib && python scripts/auth_youtube.py`, then copy the 3 printed values into Secrets.
5. **Check the first upload.** Google's docs disagree about whether uploads from new, unaudited API projects get locked to private. If your first video says *private* in YouTube Studio, fill out the free **YouTube API Services audit form** (support.google.com/youtube/contact/yt_api_form). The log prints a warning if this happens.

## 4. TikTok

1. developers.tiktok.com → create an app → add **Login Kit** and **Content Posting API**, and turn on **Direct Post**.
2. Scopes: `user.info.basic`, `video.publish`. Redirect URI: any https page you own (for example a free `yourname.github.io` page).
3. Run `python scripts/auth_tiktok.py CLIENT_KEY CLIENT_SECRET https://yourname.github.io/` and copy the 3 values into Secrets.
4. **Submit the app for TikTok's audit** (free, takes days to about 2 weeks). Until it passes, TikTok only lets the API post **private** videos, and your TikTok account has to be set to private. Once it's approved, posts go public automatically. No code change needed.

## 5. Instagram Reels (optional)

You need an Instagram **Professional** (Creator) account and a Meta developer app with the *Instagram API with Instagram Login* product and the `instagram_business_content_publish` permission. Generate a long-lived token and put it in `IG_ACCESS_TOKEN`, with your IG user ID in `IG_USER_ID`. Then set `instagram: true` in `config.yaml`. The token refreshes itself on every run.

## 6. Streamer clips (optional, read this)

Reposting a streamer's clip **without permission** gets you copyright strikes, and 3 strikes deletes the channel. So the clip format only uses streamers you list in `config.yaml` with `permission: true`. Only add someone if they publicly allow clip channels (many big streamers run clipping programs or Discord clipping rules). Clips come from the free Twitch API: dev.twitch.tv → Register app → copy the Client ID and Secret. Each clip gets a hook title, auto-captions (Whisper), and a credit tag with a link.

## 7. Your own gameplay (optional, best for growth)

Record GTA 6 clips on your console (PS5 Create button / Xbox Game Bar) and put the mp4s in `footage/` (under 100 MB each). The **gameplay story** format then narrates over your footage. Rockstar's video policy allows gameplay videos but **not story spoilers or isolated cutscenes**, so avoid recording those.

## 8. Test, then go live

* **Actions tab → autopost → Run workflow → check "dry_run"**. The run renders a video without posting it. Download it from the run page under *Artifacts*.
* For the first week, consider setting `privacy: private` in `config.yaml` to check quality before going public.
* After that it runs by itself every 3 hours. If a run fails, it shows red in the Actions tab, and GitHub emails you.

## Things to know

* **Monetization:** YouTube won't pay for "mass-produced or repetitive" AI content, and Rockstar's policy covers *non-commercial* fan videos. Growth comes first. Your own footage and ideas make the channel more original and safer to monetize later.
* **8 posts a day is a lot.** If views stall or a platform flags spam, change the cron in `.github/workflows/autopost.yml` to `17 */4 * * *` (6 a day) or `17 */6 * * *`.
* **AI labels:** TikTok's `is_aigc` and Instagram labels are on (`label_ai_content: true`). YouTube's synthetic-media flag is only meant for *realistic* fake footage, which these animated videos aren't.
* **Change topics later** by editing `topic`/`news_queries` in `config.yaml` and the starter facts in `facts.yaml`.
