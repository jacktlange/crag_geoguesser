#!/usr/bin/env python3
"""
Build today's Crag Guesser set.

  1. Reads the Mountain Project homepage slideshow (plus any photo links you
     put in data/extra_photos.txt) and adds new, usable photos to data/pool.json.
  2. Picks today's photos from the pool, least-used first, shuffled with a
     date-based seed so a re-run gives the same set.
  3. Writes site/data/daily/<date>.json, site/data/today.json and
     site/data/index.json for the game page.

If Mountain Project can't be reached, it still builds today's set from the
photos already in the pool.

Examples
  python3 scripts/daily.py                      # today, in America/Denver
  python3 scripts/daily.py --no-scrape          # skip Mountain Project, use the pool
  python3 scripts/daily.py --date 2026-11-02 --force
"""
import argparse
import datetime
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
def grow_pool(pool, today, excluded):
    """Add new usable photos from the slideshow and extra_photos.txt."""
    urls, failed = [], False
    try:
        urls += mp.slideshow_photo_urls()
        print(f"Slideshow: {len(urls)} photos on the homepage.")
        if not urls:
            warn("No slideshow photos found on the homepage. Mountain Project's layout may have changed.")
    except urllib.error.URLError as e:
        failed = True
        warn(f"Could not read the Mountain Project homepage ({e}). Using the existing pool.")
    for line in read_lines(EXTRA_PATH):
        m = re.search(r"https?://\S*?/photo/\d+\S*|/photo/\d+\S*", line)
        if m:
            urls.append(mp.absolute(m.group(0)))

    known = {p["id"] for p in pool["photos"]}
    added = 0
    for url in urls:
        pid = mp.photo_id(url)
        if not pid or pid in known or pid in pool["rejected"] or pid in excluded:
            continue
        try:
            entry, reason = mp.process_photo(url, pool["areas"])
        except urllib.error.URLError as e:
            warn(f"Could not load {url} ({e}); will retry next run.")
            continue
        if entry:
            pool["photos"].append({**entry, "addedOn": today, "usedOn": []})
            known.add(pid)
            added += 1
            print(f"  + {entry['title'][:60]} [{entry['coordArea']}]")
        elif reason.startswith("filtered"):
            pool["rejected"][pid] = reason
            print(f"  - {pid}: {reason}")
        else:
            warn(f"Photo {pid} left out for now: {reason}")
    print(f"Pool: {len(pool['photos'])} photos ({added} new, {len(pool['rejected'])} filtered out).")
    return failed


def pick(pool, count, date_str, excluded):
    """Least-used photos first; ties broken by a shuffle seeded with the date."""
    cands = sorted((p for p in pool["photos"] if p["id"] not in excluded), key=lambda p: p["id"])
    random.Random(date_str).shuffle(cands)
    cands.sort(key=lambda p: (len(p["usedOn"]), p["usedOn"][-1] if p["usedOn"] else ""))  # stable
    return cands[:count]


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
    excluded = {m.group(1) for line in read_lines(EXCLUDE_PATH) if (m := re.search(r"(\d{6,})", line))}

    if args.force:  # forget that this date used any photos, so the re-pick starts clean
        for p in pool["photos"]:
            p["usedOn"] = [d for d in p["usedOn"] if d != today]

    if not args.no_scrape:
        grow_pool(pool, today, excluded)

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

    print(f"Built #{daily['number']} for {today} with {len(chosen)} photo(s):")
    for p in chosen:
        print(f"  {p['id']}  {p['coordArea']}  ({p['lat']:.4f}, {p['lng']:.4f})")
    set_output("skip", "false")
    set_output("date", today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
