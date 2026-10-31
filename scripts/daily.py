#!/usr/bin/env python3
"""
Build today's Crag Guesser set.

  1. Reads the Mountain Project homepage slideshow (plus any photo links you
     put in data/extra_photos.txt) and adds new, usable photos to data/pool.json.
  2. Picks today's photos from the pool, least-used first, shuffled with a
     date-based seed so a re-run gives the same set.
  3. Writes site/data/daily/<date>.json, site/data/today.json,
     site/data/index.json and site/data/practice.json for the game page.

If Mountain Project can't be reached, it still builds today's set from the
photos already in the pool.

Examples
  python3 scripts/daily.py                      # today, in America/Denver
  python3 scripts/daily.py --no-scrape          # skip Mountain Project, use the pool
  python3 scripts/daily.py --date 2026-11-02 --force
"""
import argparse
import datetime
import hashlib
import json
import os
import random
import re
import sys
import urllib.error
from zoneinfo import ZoneInfo

import mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL_PATH = os.path.join(ROOT, "data", "pool.json")
EXCLUDE_PATH = os.path.join(ROOT, "data", "exclude.txt")
EXTRA_PATH = os.path.join(ROOT, "data", "extra_photos.txt")
SITE_DATA = os.path.join(ROOT, "site", "data")
DAILY_DIR = os.path.join(SITE_DATA, "daily")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def read_lines(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
    return out


def set_output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def warn(msg):
    # In GitHub Actions this shows up as a yellow annotation on the run.
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"WARNING: {msg}")


# ---------------------------------------------------------------------------
def load_excluded():
    return {m.group(1) for line in read_lines(EXCLUDE_PATH) if (m := re.search(r"(\d{6,})", line))}


POPULAR_PAGES = 20   # how far down the Popular list to look (about 40 photos a page)


def crawl_featured(sort, photo_type, is_new, target, max_requests=8):
    """Read pages of one featured list until it has `target` photos we haven't seen,
    or the list runs dry, or `max_requests` pages have been read."""
    found, new_ids, tried, dry, total = [], set(), set(), 0, None
    for _ in range(max_requests):
        if sort == "newest":
            page = len(tried) + 1
            if total and page > total:
                break
        elif sort == "popular":
            choices = [n for n in range(1, min(total or POPULAR_PAGES, POPULAR_PAGES) + 1) if n not in tried]
            if not choices:
                break
            page = random.choice(choices)
        else:
            page = 1                      # the Random list is reshuffled on every request
        tried.add(page)
        urls, total = mp.featured_page(sort, photo_type, page)
        fresh = {mp.photo_id(u) for u in urls if is_new(u)} - new_ids
        new_ids |= fresh
        found += urls
        dry = 0 if fresh else dry + 1
        if len(new_ids) >= target or dry >= 2:
            break
    return found, len(tried)


def collect_urls(sources, types, is_new=None, want=None):
    """Photo links from the chosen sources: slideshow, popular, newest, random."""
    is_new = is_new or (lambda u: True)
    slide, featured, failed = [], [], False
    if "slideshow" in sources:
        try:
            slide = mp.slideshow_photo_urls()
            print(f"Slideshow: {len(slide)} photos on the homepage.")
            if not slide:
                warn("No slideshow photos found on the homepage. Mountain Project's layout may have changed.")
        except urllib.error.URLError as e:
            failed = True
            warn(f"Could not read the Mountain Project homepage ({e}).")
    lists = [(src, t) for src in sources if src in mp.FEATURED_SORTS for t in types]
    # Aim a bit high: some candidates get filtered out or can't be read.
    per_list = max(10, -(-int((want or 10) * 1.3) // len(lists))) if lists else 0
    for src, t in lists:
        try:
            found, pages = crawl_featured(src, t, is_new, per_list)
            print(f"Featured photos ({src}, {t}): {len(found)} listed on {pages} page(s).")
            featured += found
        except urllib.error.URLError as e:
            failed = True
            warn(f"Could not read the featured photos list ({src}, {t}): {e}")
    extra = []
    for line in read_lines(EXTRA_PATH):
        m = re.search(r"https?://\S*?/photo/\d+\S*|/photo/\d+\S*", line)
        if m:
            extra.append(mp.absolute(m.group(0)))
    random.shuffle(featured)    # so a per-run cap doesn't always take the same ones
    seen, urls = set(), []
    for u in slide + extra + featured:
        pid = mp.photo_id(u)
        if pid and pid not in seen:
            seen.add(pid)
            urls.append(u)
    return urls, failed


def grow_pool(pool, today, excluded, sources=("slideshow",), max_new=None, types=("Action",), max_pool=None):
    """Add new usable photos to the pool. Returns (number added, any source failed)."""
    if max_pool and len(pool["photos"]) >= max_pool:
        print(f"The pool already has {len(pool['photos'])} photos (limit {max_pool}); not adding more.")
        return 0, False
    known = {p["id"] for p in pool["photos"]}

    def is_new(url):
        pid = mp.photo_id(url)
        return bool(pid) and pid not in known and pid not in pool["rejected"] and pid not in excluded

    urls, failed = collect_urls(sources, types, is_new, max_new)
    fails = pool.setdefault("failures", {})
    added = attempts = 0
    for url in urls:
        if max_new is not None and (added >= max_new or attempts >= max_new * 3):
            break
        if max_pool and len(pool["photos"]) >= max_pool:
            print(f"Reached the pool limit of {max_pool} photos.")
            break
        pid = mp.photo_id(url)
        if not is_new(url):
            continue
        attempts += 1
        try:
            entry, reason = mp.process_photo(url, pool["areas"])
        except urllib.error.URLError as e:
            warn(f"Could not load {url} ({e}); will retry next run.")
            continue
        if entry:
            pool["photos"].append({**entry, "addedOn": today, "usedOn": []})
            known.add(pid)
            fails.pop(pid, None)
            added += 1
            print(f"  + {entry['title'][:60]} [{entry['coordArea']}]")
        elif reason.startswith("filtered"):
            pool["rejected"][pid] = reason
            print(f"  - {pid}: {reason}")
        else:
            n = fails.get(pid, 0) + 1          # layout trouble or an album photo with no area
            if n >= 3:
                pool["rejected"][pid] = "gave up after 3 tries: " + reason
                fails.pop(pid, None)
                print(f"  - {pid}: gave up ({reason})")
            else:
                fails[pid] = n
                print(f"  ? {pid}: {reason} (try {n} of 3)")
    print(f"Pool: {len(pool['photos'])} photos ({added} new, {len(pool['rejected'])} filtered out).")
    return added, failed


PRACTICE_MODES = ("reserve", "used", "all")


def is_reserved(pid):
    """One photo in four is held back for 'Play again'. Daily puzzles only use
    those once every other photo is gone, so practicing can't spoil a puzzle."""
    return int(hashlib.sha1(pid.encode()).hexdigest(), 16) % 4 == 0


def pick(pool, count, date_str, excluded):
    """Unreserved, least-used photos first; ties broken by a shuffle seeded with the date."""
    cands = sorted((p for p in pool["photos"] if p["id"] not in excluded), key=lambda p: p["id"])
    random.Random(date_str).shuffle(cands)
    cands.sort(key=lambda p: (is_reserved(p["id"]), len(p["usedOn"]),
                              p["usedOn"][-1] if p["usedOn"] else ""))  # stable
    return cands[:count]


def practice_mode(arg=None):
    mode = arg or os.environ.get("PRACTICE_POOL") or "reserve"
    if mode not in PRACTICE_MODES:
        warn(f"PRACTICE_POOL '{mode}' isn't one of {', '.join(PRACTICE_MODES)}; using 'reserve'.")
        mode = "reserve"
    return mode


def write_practice(pool, excluded, mode, stamp):
    """Write site/data/practice.json, the photos 'Play again' draws from.
      reserve: photos already used in a puzzle, plus the reserved quarter of the pool
      used:    only photos already used in a puzzle
      all:     the whole pool (can show a photo before it appears in a puzzle)"""
    def keep(p):
        if p["id"] in excluded:
            return False
        if mode == "all":
            return True
        if mode == "used":
            return bool(p["usedOn"])
        return bool(p["usedOn"]) or is_reserved(p["id"])
    photos = [public(p) for p in sorted(pool["photos"], key=lambda p: p["id"]) if keep(p)]
    save_json(os.path.join(SITE_DATA, "practice.json"), {"generated": stamp, "source": mode, "photos": photos})
    return len(photos)


def refresh_image_urls(photos):
    """Mountain Project image URLs carry a timestamp that changes if the photo is
    replaced, so re-read each chosen photo page and keep the newest."""
    for p in photos:
        try:
            info = mp.parse_photo_page(p["photoUrl"])
            if info["imageUrl"]:
                p["imageUrl"] = info["imageUrl"]
        except urllib.error.URLError as e:
            warn(f"Could not refresh image for {p['id']} ({e}); keeping the saved URL.")


def public(p):
    keys = ("id", "photoUrl", "imageUrl", "title", "breadcrumb", "coordArea", "approx", "lat", "lng")
    return {k: p[k] for k in keys}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tz", default="America/Denver", help="time zone that defines 'today'")
    ap.add_argument("--count", type=int, default=5, help="photos per day")
    ap.add_argument("--date", help="override today's date (YYYY-MM-DD)")
    ap.add_argument("--at-hour", type=int, help="only run when it is this hour (0-23) in --tz")
    ap.add_argument("--force", action="store_true", help="rebuild the day's set if it already exists")
    ap.add_argument("--no-scrape", action="store_true", help="don't contact Mountain Project")
    ap.add_argument("--sources", default="slideshow",
                    help="comma list from: slideshow, popular, newest, random (default: slideshow)")
    ap.add_argument("--practice-pool", choices=PRACTICE_MODES, default=None,
                    help="photos 'Play again' draws from (default: $PRACTICE_POOL, else reserve)")
    args = ap.parse_args()

    now = datetime.datetime.now(ZoneInfo(args.tz))
    if args.at_hour is not None and now.hour != args.at_hour:
        print(f"It is {now:%H:%M} in {args.tz}, not {args.at_hour}:00. Nothing to do.")
        set_output("skip", "true")
        return 0

    today = args.date or now.date().isoformat()
    daily_path = os.path.join(DAILY_DIR, f"{today}.json")
    if os.path.exists(daily_path) and not args.force:
        print(f"{today} already exists. Nothing to do (use --force to rebuild).")
        set_output("skip", "true")
        return 0

    pool = load_json(POOL_PATH, {"version": 1, "areas": {}, "rejected": {}, "photos": []})
    excluded = load_excluded()

    if args.force:  # forget that this date used any photos, so the re-pick starts clean
        for p in pool["photos"]:
            p["usedOn"] = [d for d in p["usedOn"] if d != today]

    if not args.no_scrape:
        grow_pool(pool, today, excluded, sources=[x.strip() for x in args.sources.split(",") if x.strip()])

    chosen = pick(pool, args.count, today, excluded)
    if not chosen:
        save_json(POOL_PATH, pool)
        print("The pool has no usable photos, so no set could be built.", file=sys.stderr)
        return 1
    if len(chosen) < args.count:
        warn(f"Only {len(chosen)} photo(s) in the pool; today's set is short. "
             f"Add photo links to data/extra_photos.txt to grow it.")

    if not args.no_scrape:
        refresh_image_urls(chosen)

    for p in chosen:
        p["usedOn"].append(today)
    save_json(POOL_PATH, pool)

    dates = sorted({f[:-5] for f in os.listdir(DAILY_DIR) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f)}
                   | {today}) if os.path.isdir(DAILY_DIR) else [today]
    daily = {
        "date": today,
        "number": dates.index(today) + 1,
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "photos": [public(p) for p in chosen],
    }
    save_json(daily_path, daily)
    save_json(os.path.join(SITE_DATA, "today.json"), daily)
    save_json(os.path.join(SITE_DATA, "index.json"), {"dates": sorted(dates, reverse=True)})

    n_practice = write_practice(pool, excluded, practice_mode(args.practice_pool), daily["generated"])

    print(f"Built #{daily['number']} for {today} with {len(chosen)} photo(s); Play again has {n_practice}:")
    for p in chosen:
        print(f"  {p['id']}  {p['coordArea']}  ({p['lat']:.4f}, {p['lng']:.4f})")
    set_output("skip", "false")
    set_output("date", today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
