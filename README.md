# Crag Guesser

A daily GeoGuessr-style game for a Discord channel, using climbing photos from the
Mountain Project homepage slideshow. Every weekday morning a GitHub Action:

1. adds new slideshow photos to a pool (skipping ice, snow, maps and drawings),
2. picks the day's photos (least-used first, same set for everyone),
3. publishes the game page on GitHub Pages,
4. posts a link to your Discord channel.

Players guess on a map, see their distance and score, and copy a Wordle-style
result like this to paste in the channel:

```
Crag Guesser #12 (11/4) · 14,200/25,000
🟩🟨🟥🟩🟨
https://yourname.github.io/crag-guesser/
```

Guesses are scored in the browser and kept in that browser, so this is an
honor-system game: one try per person per day is enforced only by the page,
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

The homepage slideshow only has a handful of photos and changes slowly, so the
pool starts small and a short set (or repeats) is normal at first. To add more:

- Paste Mountain Project photo links into `data/extra_photos.txt`, one per
  line. They go through the same filters and GPS lookup.
- Use the **Run workflow** button whenever you want the pool to refresh sooner.

## Removing a photo

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
  and identifies itself. Please keep it that way.
- Scoring: `5000 × e^(−distance ÷ 1500 km)` per photo, up to 5,000.
  Squares: 🟩 4,000+, 🟨 2,500+, 🟧 1,000+, 🟥 less, ⬛ skipped.

## Layout

```
.github/workflows/daily.yml   the schedule, deploy, and Discord steps
scripts/mp.py                 Mountain Project scraping and filters
scripts/daily.py              builds the day's set
scripts/post_discord.py       posts to Discord
data/pool.json                every usable photo so far (not published)
data/exclude.txt              photos to never use
data/extra_photos.txt         photo links to add to the pool
site/                         what gets published: the game page and daily data
```
