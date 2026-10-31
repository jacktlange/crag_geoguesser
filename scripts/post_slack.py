#!/usr/bin/env python3
"""
Post today's Crag Guesser announcement to Slack through an incoming webhook.

Environment
  SLACK_WEBHOOK_URL   required (unless --dry-run); keep it in a repository secret
  PAGES_URL           optional; the game's address. Defaults to
                      https://<owner>.github.io/<repo>/ from GITHUB_REPOSITORY

  python3 scripts/post_slack.py --dry-run     # print the message instead of posting
"""
import datetime
import json
import os
import sys
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


def slack_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message():
    today = load(os.path.join(SITE_DATA, "today.json"))
    d = datetime.date.fromisoformat(today["date"])
    n = len(today["photos"])
    url = pages_url() or "(set the PAGES_URL repository variable to add the link)"

    lines = [
        f":mountain: *Crag Guesser #{today['number']}: {d:%a, %b} {d.day}*",
        f"{n} photo{'s' if n != 1 else ''} today. Guess where each was taken, then paste your result here to compare.",
        f"<{url}|Play today's round>" if url.startswith("http") else url,
    ]

    # Yesterday's answers (the previous puzzle in the archive).
    try:
        dates = load(os.path.join(SITE_DATA, "index.json"))["dates"]
        prev = next((x for x in dates if x < today["date"]), None)
        if prev:
            old = load(os.path.join(SITE_DATA, "daily", f"{prev}.json"))
            links = ", ".join(
                f"<{p['photoUrl']}|{slack_escape(p['coordArea'])}>" for p in old["photos"])
            lines += ["", f"_Last round's answers:_ {links}"]
    except (OSError, ValueError, KeyError):
        pass
    return "\n".join(lines)


def main():
    text = build_message()
    if "--dry-run" in sys.argv:
        print(text)
        return 0
    hook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not hook:
        print("SLACK_WEBHOOK_URL is not set; not posting.", file=sys.stderr)
        return 1
    req = urllib.request.Request(
        hook, data=json.dumps({"text": text, "unfurl_links": False}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    print("Slack replied:", body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
