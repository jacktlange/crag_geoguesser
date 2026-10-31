#!/usr/bin/env python3
"""
Add fresh photos to data/pool.json without building a puzzle.

Run on a schedule by .github/workflows/refresh-pool.yml. Each run looks at the
Mountain Project homepage slideshow (which rotates) and a page from the
"featured photos" lists, and adds new photos that pass the filters, up to
--max-new per run so it stays gentle on the site.

  python3 scripts/refresh_pool.py
  python3 scripts/refresh_pool.py --sources slideshow,popular --max-new 5
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
    ap.add_argument("--max-new", type=int, default=12, help="most photos to add per run")
    ap.add_argument("--tz", default="America/Denver")
    args = ap.parse_args()

    today = datetime.datetime.now(ZoneInfo(args.tz)).date().isoformat()
    pool = daily.load_json(daily.POOL_PATH, {"version": 1, "areas": {}, "rejected": {}, "photos": []})
    excluded = daily.load_excluded()

    added, failed = daily.grow_pool(
        pool, today, excluded,
        sources=[x.strip() for x in args.sources.split(",") if x.strip()],
        max_new=args.max_new,
        types=[x.strip() for x in args.types.split(",") if x.strip()])
    daily.save_json(daily.POOL_PATH, pool)

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
