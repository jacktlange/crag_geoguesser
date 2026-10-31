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

The schedule runs at two UTC hours and the script only goes ahead when it is
`POST_HOUR` in `TZ_NAME`, so daylight saving changes are handled. GitHub can
start scheduled runs several minutes late, which is normal.

## Growing the photo pool

Three scheduled workflows keep things running. They all share one queue, so they
never edit the pool at the same time.

| Workflow | When | What it does |
| --- | --- | --- |
| **Poll slideshow** (`poll-slideshow.yml`) | every hour | Looks at the homepage slideshow and adds up to 6 new photos. Most hours nothing new has rotated in, so it makes one request and saves nothing. It doesn't republish the site. |
| **Refresh photo pool** (`refresh-pool.yml`) | every 6 hours | Adds up to 100 new photos from the sources below, then republishes the site's photo library. |
| **Daily Crag Guesser** (`daily.yml`) | weekdays, 8 am | Builds and posts the day's puzzle. |

The refresh job reads, in this order of importance:

1. **Regions:** random samples from each state's "All Photos Within" list
   (`featured-photos?locationId=…`), choosing states in proportion to the
   square root of their route counts (so California and Colorado come up more
   than Delaware, but not overwhelmingly). Each request returns about 40 random
   photos from that state, and a state that stops yielding new photos is
   dropped. This is what lets the pool grow past a few hundred photos, because
   it reaches all of Mountain Project rather than only its featured photos. Add
   `--international` to the command to include Europe, Asia and the rest.
2. **Featured lists:** random pages of the Popular list, the first pages of the
   Newest list, and the Random list, limited to the *Action / Scenic* type
   (which leaves out the *Beta* type, where topos and route overlays live).
3. **The slideshow**, again.

Every new photo goes through the same filters and GPS lookup. A run adds up to
100 photos (roughly 5 to 10 minutes, with a pause between requests) and stops
once the pool reaches **10,000 photos**, which is the default `--max-pool`.
Raise or lower it if you like. Photos that can't be read (for example album
photos that aren't attached to an area) are retried twice and then given up on.
If fewer than 15 unused photos are left, a run shows a yellow warning.

**How long to 10,000, and what it costs Mountain Project:** at 100 photos per
run and 4 runs a day, the pool reaches 10,000 in about 25 days. Each photo takes
a request for its page, plus one for its area the first time that area is seen,
so the whole build is on the order of 15,000 to 20,000 requests, spread over
those weeks and made one at a time, 1.5 seconds apart. To go gentler, edit the
`cron` line in `refresh-pool.yml` (for example once a day), lower `--max-new`,
or raise the pause by setting `MP_DELAY` (seconds). Once the pool is where you
want it, you can switch the refresh workflow off entirely from the Actions tab.

Where to change things: the `cron` lines set how often each workflow runs, and
`--max-new`, `--max-pool`, `--sources` (`slideshow,regions,popular,newest,random`)
and `--types` (`Action`, or `Action,Historical` to include old historic photos)
go on the `python3 scripts/refresh_pool.py` lines. To run either one right now:
**Actions → the workflow's name → Run workflow**.

The pool file (`data/pool.json`) is about 650 bytes per photo, so around 6 MB at
10,000 photos. The photo library on the site (see Play again below) is capped at
1,500 photos (set `LIBRARY_MAX` to change it) so the page stays quick to load.

You can also paste Mountain Project photo links into `data/extra_photos.txt`,
one per line, and they'll be added on the next run.

## Play again

After a puzzle's results screen, **Play again** starts a practice round of 5
photos. Practice rounds aren't saved, can't be posted to Discord, and don't
change today's score.

**One library, not two.** The site keeps a single file of photos,
`site/data/photos.json`, and both the daily puzzle and Play again use it. A
day's puzzle (`site/data/daily/<date>.json`) is just a list of photo IDs from
that library, so each photo is stored once. The library holds every photo
that has already been used in a puzzle, plus a reserved quarter of the pool
that daily puzzles never pick (unless they run out of others). That means
practicing can never show anyone a photo that is still to come in a daily
puzzle, and the library has plenty of variety from the start.

**Always a different set.** Each browser deals practice photos like a deck: ones
it has never shown come first, in random order, then the ones shown longest
ago, so a photo only comes round again after all the others have been dealt.
Photos from today's puzzle go last, and the 5 photos in a set count as dealt as
soon as the set starts, so reloading the page also gives a new set. Consecutive
sets never share a photo as long as the library has more than about 10 photos.
If the library is smaller than that, the results screen says so, and sets will
repeat until it grows. The library grows whenever the refresh job or a daily
puzzle runs; you can see it at `<your site>/data/photos.json`.

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
  most 100 photos per run in the refresh job (6 per run in the hourly poll), and the pool stops at 10,000.
- Scoring: `5000 × e^(−distance ÷ 1500 km)` per photo, up to 5,000.
  Squares: 🟩 4,000+, 🟨 2,500+, 🟧 1,000+, 🟥 less, ⬛ skipped.

## Layout

```
.github/workflows/daily.yml   the daily schedule, deploy, and Discord steps
.github/workflows/refresh-pool.yml   the every-6-hours photo pool refresh
.github/workflows/poll-slideshow.yml   the hourly slideshow check
scripts/mp.py                 Mountain Project scraping and filters
scripts/daily.py              builds the day's set and the site's photo library
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
