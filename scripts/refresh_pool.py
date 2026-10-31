#!/usr/bin/env python3
"""
Add fresh photos to data/pool.json without building a puzzle.

Run on a schedule by .github/workflows/refresh-pool.yml. Each run looks at the
Mountain Project homepage slideshow (which rotates) and a page from the
"featured photos" lists, and adds new photos that pass the filters, up to
--max-new per run so it stays gentle on the site.

  python3 scripts/refresh_pool.py
  python3 scripts/refresh_pool.py --sources slideshow,popular --max-new 5
  python3 scripts/refresh_pool.py --max-new 100 --max-pool 2000   # the defaults
  python3 scripts/refresh_pool.py --types Action,Historical
"""
import argparse
import datetime
import os
import sys
from zoneinfo import ZoneInfo

import daily


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default="slideshow,popular,newest,random",
                    help="comma list from: slideshow, popular, newest, random")
    ap.add_argument("--types", default="Action",
                    help="featured-photo types: Action (action/scenic) and/or Historical; comma list")
    ap.add_argument("--max-new", type=int, default=100, help="most photos to add per run")
    ap.add_argument("--max-pool", type=int, default=2000, help="stop adding once the pool is this big")
    ap.add_argument("--tz", default="America/Denver")
    ap.add_argument("--practice-pool", choices=daily.PRACTICE_MODES, default=None,
                    help="photos 'Play again' draws from (default: $PRACTICE_POOL, else reserve)")
    args = ap.parse_args()

    today = datetime.datetime.now(ZoneInfo(args.tz)).date().isoformat()
    pool = daily.load_json(daily.POOL_PATH, {"version": 1, "areas": {}, "rejected": {}, "photos": []})
    excluded = daily.load_excluded()

    added, failed = daily.grow_pool(
        pool, today, excluded,
        sources=[x.strip() for x in args.sources.split(",") if x.strip()],
        max_new=args.max_new,
        max_pool=args.max_pool,
        types=[x.strip() for x in args.types.split(",") if x.strip()])
    daily.save_json(daily.POOL_PATH, pool)

    # Keep the "Play again" list in step with the pool, so it grows without waiting for a puzzle.
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    n_practice = daily.write_practice(pool, excluded, daily.practice_mode(args.practice_pool), stamp)
    print(f"Play again now draws from {n_practice} photos.")

    unused = sum(1 for p in pool["photos"] if not p["usedOn"] and p["id"] not in excluded)
    print(f"Added {added}. {len(pool['photos'])} photos in the pool, {unused} not yet used in a puzzle.")
    if unused < 15:
        daily.warn(f"Only {unused} unused photos left in the pool. Puzzles will start repeating photos soon.")
    if failed and added == 0:
        daily.warn("Mountain Project could not be reached, so nothing new was added.")
    daily.set_output("added", str(added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
