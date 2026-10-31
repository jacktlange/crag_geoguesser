#!/usr/bin/env python3
"""
Post today's Crag Guesser announcement to a Discord channel through a webhook.

Environment
  DISCORD_WEBHOOK_URL   required (unless --dry-run); keep it in a repository secret
  PAGES_URL             optional; the game's address. Defaults to
                        https://<owner>.github.io/<repo>/ from GITHUB_REPOSITORY

  python3 scripts/post_discord.py --dry-run     # print the message instead of posting
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, "site", "data")


def pages_url():
    url = os.environ.get("PAGES_URL", "").strip()
    if not url:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if "/" in repo:
            owner, name = repo.split("/", 1)
            url = f"https://{owner.lower()}.github.io/{name}/"
    return url if url.endswith("/") or not url else url + "/"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def md_escape(s):
    """Escape Discord markdown characters so area names show as plain text."""
    return re.sub(r"([\\*_~`|\[\]()>#])", r"\\\1", s)


def build_message():
    today = load(os.path.join(SITE_DATA, "today.json"))
    d = datetime.date.fromisoformat(today["date"])
    n = len(today["photos"])
    url = pages_url()

    lines = [
        f":mountain: **Crag Guesser #{today['number']}: {d:%a, %b} {d.day}**",
        f"{n} photo{'s' if n != 1 else ''} today. Guess where each was taken, then paste your result here to compare.",
        f"[Play today's round]({url})" if url else "(set the PAGES_URL repository variable to add the link)",
    ]

    # Last round's answers (the previous puzzle in the archive).
    try:
        dates = load(os.path.join(SITE_DATA, "index.json"))["dates"]
        prev = next((x for x in dates if x < today["date"]), None)
        if prev:
            old = load(os.path.join(SITE_DATA, "daily", f"{prev}.json"))
            links = ", ".join(f"[{md_escape(p['coordArea'])}]({p['photoUrl']})" for p in old["photos"])
            lines += ["", f"_Last round's answers:_ {links}"]
    except (OSError, ValueError, KeyError):
        pass
    return "\n".join(lines)[:1990]   # Discord's limit is 2000 characters


def main():
    text = build_message()
    if "--dry-run" in sys.argv:
        print(text)
        return 0
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not hook:
        print("DISCORD_WEBHOOK_URL is not set; not posting.", file=sys.stderr)
        return 1
    payload = {
        "content": text,
        "flags": 4,                           # no link preview cards
        "allowed_mentions": {"parse": []},    # never ping anyone
    }
    # Discord rejects Python's default User-Agent, so send our own.
    req = urllib.request.Request(
        hook, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "crag-guesser (personal project)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Discord replied:", r.status)
    except urllib.error.HTTPError as e:
        print(f"Discord rejected the post: {e.code} {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
