# Crag Guesser

A daily GeoGuessr-style game for a Discord channel, using climbing photos from the
Mountain Project homepage slideshow. Every weekday morning a GitHub Action:

1. adds new slideshow photos to a pool (skipping ice, snow, maps and drawings),
2. picks the day's photos (least-used first, same set for everyone),
3. publishes the game page on GitHub Pages,
4. posts a link to your Discord channel.

Players guess on a map, see their distance and score, and copy a Wordle-style
result like this to paste in the channel. When they finish they can hit
**Play again** for an extra practice round.

```
Crag Guesser #12 (11/4) · 14,200/25,000
🟩🟨🟥🟩🟨
https://yourname.github.io/crag-guesser/
```

Guesses are scored in the browser and kept in that browser. With the optional
relay below, players can also post their result to the channel with one click.
It is an honor-system game: one try per person per day is enforced only by the page,
and the answers are visible to anyone who opens the page's data. There is no
shared leaderboard; people compare pasted results in Discord.

## Setup (about 15 minutes)

1. **Create a public GitHub repository** (GitHub Pages is free for public
   repositories) and push everything in this folder to its `main` branch.
2. **Turn on Pages from Actions:** repository **Settings → Pages → Build and
   deployment → Source: GitHub Actions**.
3. **Allow the job to save the day's set:** **Settings → Actions → General →
   Workflow permissions → Read and write permissions**.
4. **Create a Discord webhook:** you need the *Manage Webhooks* permission on
   the server. Open the channel's settings (gear icon) → **Integrations →
   Webhooks → New Webhook**, pick the channel, and click **Copy Webhook URL**.
   Treat the URL like a password: anyone who has it can post to the channel.
5. **Save the webhook as a secret:** **Settings → Secrets and variables →
   Actions → New repository secret**, name `DISCORD_WEBHOOK_URL`.
6. **Run it once by hand:** **Actions → Daily Crag Guesser → Run workflow**.
   This builds the first set, publishes the page, and posts to Discord. Open the
   link in the Discord message to check that photos and the map load.

After that it runs by itself on weekdays.

If your site address isn't `https://<owner>.github.io/<repo>/` (for example you
use a custom domain), add a repository **variable** named `PAGES_URL` with the
full address.

## Let players post their result to Discord (optional)

Without this, players copy their result and paste it into the channel
themselves. With it, a **Post to Discord** button on the results screen posts
it for them, as a message like:

```
**Alex** · Crag Guesser #12 (11/4) · 14,200/25,000
🟩🟨🟥🟩🟨
_12 mi · 340 mi · 1,204 mi · 8 mi · 91 mi_
```

The game page can't be given your webhook URL, because anyone could read it
from the page source and post to your channel. So a tiny relay (a Cloudflare
Worker, free) keeps the webhook secret, checks the result looks sane, and
posts it. Setup takes about 10 minutes:

1. Make a free account at <https://dash.cloudflare.com>. Go to **Workers &
   Pages → Create → Create Worker**, name it `crag-guesser`, and **Deploy**
   (the sample "Hello World" code is fine for now).
2. Click **Edit code**, delete the sample, paste in the whole of
   `worker/index.js`, and **Deploy** again.
3. Open the Worker's **Settings → Variables and Secrets** and add:
   - `DISCORD_WEBHOOK_URL`, type **Secret**, set to your Discord webhook URL
   - `ALLOWED_ORIGIN`, type **Text**, set to your game's address without the
     path or a trailing slash, for example `https://yourname.github.io`
4. Recommended: add a KV namespace so a name can post only once per puzzle and
   one connection can't flood the channel. Go to **Storage & Databases → KV →
   Create** (any name), then in the Worker's **Settings → Bindings → Add →
   KV namespace**, use the variable name `POSTS`.
5. Copy the Worker's address (it looks like
   `https://crag-guesser.<your-account>.workers.dev`). Open `site/config.js` in
   your repository, put it in as `submitUrl`, and commit. The push redeploys
   the page.
6. Play a round on your site, type a name, and click **Post to Discord**.

What to know:

- **Names are self-reported.** Players type any name they like, and scores are
  reported by the page, not verified. The relay refuses out-of-range scores,
  old puzzles, repeat names (with KV), and sites other than yours, but someone
  who deliberately fakes a result can still post one.
- **Verified identities need Discord login.** If you want each result tied to
  a real Discord account, that needs a "Log in with Discord" step and a small
  server component. It's doable; ask for it as a next step.
- **If it gets abused:** delete the Worker (or change `ALLOWED_ORIGIN`), or
  make a new Discord webhook and update the secret.
- The free Cloudflare plan allows far more requests than a Discord server will
  ever send.

## Settings

All in `.github/workflows/daily.yml`:

| Setting | Default | Where |
| --- | --- | --- |
| Time zone that defines "today" | `America/Denver` | `TZ_NAME` |
| Hour to post (0-23, local) | `8` | `POST_HOUR` |
| Photos per day | `5` | `PHOTOS_PER_DAY` |
| Days of the week | Mon-Fri | the `cron` line (`1-5`; use `*` for every day) |
| Photos used by Play again | `used` | `PRACTICE_POOL` (`used` or `all`) |

The schedule runs at two UTC hours and the script only goes ahead when it is
`POST_HOUR` in `TZ_NAME`, so daylight saving changes are handled. GitHub can
start scheduled runs several minutes late, which is normal.

## Growing the photo pool

A second workflow, **Refresh photo pool** (`.github/workflows/refresh-pool.yml`),
runs every 6 hours and adds fresh photos so the puzzles don't run out. Each run:

1. reads the homepage slideshow (it rotates, so sampling it regularly catches
   photos you'd otherwise miss),
2. reads Mountain Project's "featured photos" lists: a random page of the
   **Popular** list, the **Newest** list, and the **Random** list, limited to
   the *Action / Scenic* type (which leaves out the *Beta* type, where topos
   and route overlays live),
3. runs each new photo through the same filters and GPS lookup, and adds up to
   12 new ones (about a minute, with a pause between requests),
4. saves `data/pool.json`. Nothing is published, so upcoming puzzles stay hidden.

If fewer than 15 unused photos are left, the run shows a yellow warning.
Photos that can't be read (for example album photos that aren't attached to an
area) are retried twice and then given up on.

To tune it, edit `refresh-pool.yml`: the `cron` line sets how often it runs,
and `--max-new`, `--sources` (`slideshow,popular,newest,random`) and `--types`
(`Action`, or `Action,Historical` to include old historic photos) go on the
`python3 scripts/refresh_pool.py` line. To run it right now: **Actions →
Refresh photo pool → Run workflow**.

You can also paste Mountain Project photo links into `data/extra_photos.txt`,
one per line, and they'll be added on the next run.

## Play again

After a puzzle's results screen, **Play again** starts a practice round of up
to 5 random photos from past puzzles (never the ones in today's puzzle when
there are others to choose from). Practice rounds aren't saved, can't be
posted to Discord, and don't change today's score.

By default practice only uses photos that have already appeared in a daily
puzzle, so practicing can never give away an upcoming puzzle. The catch is that
in the first few days there aren't many past photos, so practice will repeat
them. Set `PRACTICE_POOL: all` in `daily.yml` to practice with the whole pool
instead, which gives more variety but can show someone a photo before it turns
up in a daily puzzle.

## Removing a photo

**Players can hide photos for themselves.** Every photo has a **This is not a
climbing photo** button. After a confirmation it skips the photo and remembers
it in that browser, so it never shows up for that player again. In the daily
puzzle everyone shares the same photos, so a skipped round scores 0 for that
player (shown as ⬛ in their result); in practice rounds another photo is
swapped in. A note at the bottom of the page shows how many photos are hidden
and has a **Show them again** link. This is per browser: it doesn't affect other
players, and it doesn't remove anything from the pool. To remove a photo for
everyone, use `exclude.txt` below.

**Removing it for everyone:**

- Put its ID or link in `data/exclude.txt` and it will never be picked.
- To replace a bad photo in today's set: add it to `exclude.txt`, push, then
  **Run workflow** with **Rebuild today's set** checked. People who already
  played today start fresh if the photos in the set changed.
- To change what the filters catch, edit the word lists at the top of
  `scripts/mp.py`. Filtered photos are remembered in `data/pool.json` under
  `rejected`; delete an entry there to try that photo again.

## When something goes wrong

- **Discord gets a "daily run failed" message:** open the link in it to see the
  log. Yellow warnings in a successful run (for example "could not read the
  homepage") mean the game still ran from the existing pool.
- **Mountain Project blocks GitHub's servers or changes its layout:** the run
  keeps using the pool, and you'll see warnings. Run `python3 scripts/daily.py`
  on your own computer to add photos, commit `data/pool.json`, and push.
- **Photos don't load in the game:** Mountain Project may block images shown
  on other sites. The page offers a skip button (0 points) for any photo that
  fails, but if every photo fails, tell me and we'll switch approach.
- **No photos yet message on the page:** the workflow hasn't run, or hasn't
  been allowed to push (step 3).

## Running it on your computer

```
python3 scripts/daily.py --date 2026-11-04       # build a set (needs internet)
python3 scripts/daily.py --no-scrape             # build from the pool only
python3 scripts/refresh_pool.py --max-new 5      # add a few fresh photos to the pool
python3 scripts/post_discord.py --dry-run        # preview the Discord message
python3 -m http.server -d site                   # then open http://localhost:8000
```

If Python reports `CERTIFICATE_VERIFY_FAILED`, run `pip3 install certifi`
(or, as a last resort, set `MP_INSECURE=1` for that command).

## Notes

- Photos belong to their contributors. The game links to Mountain Project's
  images and credits the site; check Mountain Project's terms before sharing
  it beyond a private group.
- The scraper reads public pages slowly (about 1.5 seconds between requests)
  and identifies itself. Please keep it that way. The refresh job can add at
  most 12 photos per run, 4 runs a day.
- Scoring: `5000 × e^(−distance ÷ 1500 km)` per photo, up to 5,000.
  Squares: 🟩 4,000+, 🟨 2,500+, 🟧 1,000+, 🟥 less, ⬛ skipped.

## Layout

```
.github/workflows/daily.yml   the daily schedule, deploy, and Discord steps
.github/workflows/refresh-pool.yml   the every-6-hours photo pool refresh
scripts/mp.py                 Mountain Project scraping and filters
scripts/daily.py              builds the day's set and the Play again list
scripts/refresh_pool.py       adds fresh photos to the pool (run by the refresh workflow)
scripts/post_discord.py       posts the daily announcement to Discord
worker/index.js               optional relay that posts players' results (Cloudflare Worker)
worker/wrangler.toml          optional settings if you deploy the Worker from the command line
data/pool.json                every usable photo so far (not published)
data/exclude.txt              photos to never use
data/extra_photos.txt         photo links to add to the pool
site/                         what gets published: the game page and daily data
site/config.js                one setting: the relay's address (leave empty to turn off posting)
```
