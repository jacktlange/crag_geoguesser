"""
Mountain Project helpers for Crag Guesser (standard library only).

- slideshow_photo_urls(): photo links from the homepage slideshow
- process_photo(): photo page -> image URL, caption, area path, GPS, with filters

Set MP_DEBUG=1 for verbose output, MP_DELAY=<seconds> to change the pause
between requests, MP_INSECURE=1 to skip certificate checks (last resort).
"""
import html
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.request

BASE = "https://www.mountainproject.com"
UA = "Mozilla/5.0 (compatible; crag-guesser-hobby-project/1.0)"
DELAY = float(os.environ.get("MP_DELAY", "1.5"))
DEBUG = bool(os.environ.get("MP_DEBUG"))


def _ssl_context():
    if os.environ.get("MP_INSECURE"):
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX = _ssl_context()


def log(*a):
    if DEBUG:
        print("   ", *a)


# ---------------------------------------------------------------------------
# What to leave out (edit freely). The script can't see pixels, so it judges
# by caption, route grade and area path. Anything it misses can be listed in
# data/exclude.txt.
# ---------------------------------------------------------------------------
ICE_SNOW_CAPTION = re.compile(r"\b(ice|icy|icicles?|icefall|frozen|snow\w*|WI\d)\b", re.I)
ICE_SNOW_GRADE = re.compile(r"\b(?:WI|AI)\d|\bM\d{1,2}[+-]?(?=[\s)]|$)|Steep Snow|\bIce\b|\bMixed\b")
NOT_A_PHOTO_CAPTION = re.compile(
    r"\b(topos?|maps?|sketch\w*|drawings?|drawn|diagrams?|illustrations?|schematics?|scans?|screenshots?)\b", re.I)


def skip_reason(info):
    """Why a photo should be left out, or None to keep it."""
    if NOT_A_PHOTO_CAPTION.search(info["title"]):
        return "looks like a map, topo, or drawing (caption)"
    if ICE_SNOW_CAPTION.search(info["title"]):
        return "ice or snow (caption)"
    if ICE_SNOW_GRADE.search(info["breadcrumb"]):
        return "ice, mixed, or snow route (grade or area)"
    return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def get(url, retries=2):
    """GET a page as text, retrying a couple of times, then pausing politely."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                data = r.read().decode("utf-8", "replace")
            time.sleep(DELAY)
            return data
        except urllib.error.URLError as e:
            last = e
            # 403/404 won't improve by retrying
            if isinstance(e, urllib.error.HTTPError) and e.code in (403, 404):
                break
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def absolute(u):
    u = html.unescape(u)
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def clean_name(name, url):
    """Breadcrumb labels are cut off with an ellipsis; rebuild them from the URL slug."""
    if name.endswith("\u2026") or name.endswith("..."):
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        return slug.replace("-", " ").title()
    return name


def meta(page, prop):
    for pat in (
        r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)["\']' % re.escape(prop),
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop),
    ):
        m = re.search(pat, page, re.I)
        if m:
            return html.unescape(m.group(1))
    return ""


def photo_id(url):
    m = re.search(r"/photo/(\d+)", url)
    return m.group(1) if m else None


def slideshow_photo_urls():
    page = get(BASE + "/")
    # The "More Top Photos" link comes right after the slideshow.
    end = page.find("featured-photos")
    scope = page[:end] if end > 0 else page
    seen, urls = set(), []
    for m in re.finditer(r'href="((?:https://www\.mountainproject\.com)?/photo/(\d+)/[^"#?]*)"', scope):
        if m.group(2) not in seen:
            seen.add(m.group(2))
            urls.append(absolute(m.group(1)))
    return urls


FEATURED_URL = BASE + "/featured-photos"
FEATURED_SORTS = {"popular": "Popular", "newest": "Newest", "random": "Random"}


def _photo_links(page):
    seen, urls = set(), []
    for m in re.finditer(r'href="((?:https://www\.mountainproject\.com)?/photo/(\d+)/[^"#?]*)"', page):
        if m.group(2) not in seen:
            seen.add(m.group(2))
            urls.append(absolute(m.group(1)))
    return urls


# Top-level regions from Mountain Project's route guide (https://www.mountainproject.com/route-guide):
# (area ID, name, number of routes). Every area has an "All Photos Within ..." list at
# featured-photos?locationId=<ID>, so these let the job sample photos from across the whole site.
REGIONS = [
    (105905173, "Alabama", 2437), (105909311, "Alaska", 2731), (105708962, "Arizona", 15231),
    (105901027, "Arkansas", 3766), (105708959, "California", 48617), (105708956, "Colorado", 39371),
    (105806977, "Connecticut", 3170), (106861605, "Delaware", 77), (111721391, "Florida", 140),
    (105897947, "Georgia", 1948), (106316122, "Hawaii", 464), (105708958, "Idaho", 5700),
    (105911816, "Illinois", 2610), (112389571, "Indiana", 269), (106092653, "Iowa", 745),
    (107235316, "Kansas", 391), (105868674, "Kentucky", 4954), (116720343, "Louisiana", 41),
    (105948977, "Maine", 2535), (106029417, "Maryland", 3112), (105908062, "Massachusetts", 6483),
    (106113246, "Michigan", 1629), (105812481, "Minnesota", 2610), (108307056, "Mississippi", 117),
    (105899020, "Missouri", 2469), (105907492, "Montana", 4555), (116096758, "Nebraska", 14),
    (105708961, "Nevada", 7410), (105872225, "New Hampshire", 8512), (106374428, "New Jersey", 955),
    (105708964, "New Mexico", 6996), (105800424, "New York", 6700), (105873282, "North Carolina", 4312),
    (106598130, "North Dakota", 74), (105994953, "Ohio", 2790), (105854466, "Oklahoma", 2522),
    (105708965, "Oregon", 6490), (105913279, "Pennsylvania", 4515), (106842810, "Rhode Island", 2084),
    (107638915, "South Carolina", 380), (105708963, "South Dakota", 4251), (105887760, "Tennessee", 4835),
    (105835804, "Texas", 4251), (105708957, "Utah", 20349), (105891603, "Vermont", 2726),
    (105852400, "Virginia", 7229), (105708966, "Washington", 13451), (105855459, "West Virginia", 6229),
    (105708968, "Wisconsin", 5442), (105708960, "Wyoming", 7596),
]
INTERNATIONAL = [
    (105907756, "Australia", 1707), (106135596, "Africa", 2786), (106660030, "Europe", 23771),
    (106661469, "North America (outside the US)", 34058), (106661515, "Asia", 9428),
    (106661603, "South America", 4325), (107833406, "Oceania", 1413),
]


def featured_page(sort, photo_type="Action", page=1, location_id=0):
    """One page of Mountain Project's photo list for a location (0 = everywhere).

    sort: popular, newest, or random. photo_type: Action (action and scenic
    photos, which leaves out the Beta type that holds topos and overlays) or
    Historical. Returns (photo links on the page, total number of pages)."""
    url = f"{FEATURED_URL}?sort={FEATURED_SORTS[sort]}&locationId={location_id}&type={photo_type}"
    if page > 1:
        url += f"&page={page}"
    page_html = get(url)
    m = re.search(r"\b\d+\s+of\s+(\d+)\b", strip_tags(page_html))   # pagination reads "1 of 14"
    return _photo_links(page_html), int(m.group(1)) if m else 1


def parse_photo_page(url):
    page = get(url)
    image = absolute(meta(page, "og:image")) if meta(page, "og:image") else ""
    title = meta(page, "og:title") or meta(page, "title")
    title = re.sub(r"\s*[|\u2013\u2014-]\s*Mountain Project\s*$", "", title).strip()

    # The breadcrumb sits above the main photo (before the "photo/full/" link).
    cut = page.find("/photo/full/")
    crumb_html = page[:cut] if cut > 0 else page
    start = crumb_html.find("All Locations")
    if start > 0:
        crumb_html = crumb_html[start:]

    areas = []
    for m in re.finditer(r'<a[^>]+href="((?:https://www\.mountainproject\.com)?/area/(\d+)/[^"]*)"[^>]*>(.*?)</a>',
                         crumb_html, re.S):
        u = absolute(m.group(1))
        areas.append({"url": u, "name": clean_name(strip_tags(m.group(3)), u)})
    route = None
    m = re.search(r'<a[^>]+href="((?:https://www\.mountainproject\.com)?/route/(\d+)/[^"]*)"[^>]*>(.*?)</a>',
                  crumb_html, re.S)
    if m:
        u = absolute(m.group(1))
        route = {"url": u, "name": clean_name(strip_tags(m.group(3)), u)}

    names = [a["name"] for a in areas] + ([route["name"]] if route else [])
    log("photo:", url, "\n      image:", image, "\n      crumb:", " > ".join(names))
    return {"photoUrl": url, "imageUrl": image, "title": title, "areas": areas, "breadcrumb": " > ".join(names)}


GPS_PATTERNS = [
    r"GPS:?(?:\s|&nbsp;|<[^>]*>)*(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)",
    r"(?:maps\.google\.com|google\.com/maps)[^\"'<>]*?[?&;](?:q|ll|query|destination|daddr)=(-?\d{1,3}\.\d+)(?:,|%2C)\s*(-?\d{1,3}\.\d+)",
    r"\"lat(?:itude)?\"\s*:\s*(-?\d{1,3}\.\d+)\s*,\s*\"(?:lng|lon|long|longitude)\"\s*:\s*(-?\d{1,3}\.\d+)",
    r"data-lat=\"(-?\d{1,3}\.\d+)\"[^>]*data-(?:lng|lon)=\"(-?\d{1,3}\.\d+)\"",
]


def area_info(url, cache):
    """Area page -> {"lat","lng","name"} (lat/lng None if the area has no GPS).
    Results are kept in `cache`, which the caller saves between runs.
    Network errors are not cached and propagate."""
    if url in cache:
        return cache[url]
    page = get(url)
    name = None
    h = re.search(r"<h1[^>]*>\s*(.*?)\s+Rock Climbing\s*</h1>", page, re.S | re.I)
    if h:
        name = strip_tags(h.group(1)) or None
    lat = lng = None
    for pat in GPS_PATTERNS:
        m = re.search(pat, page, re.I)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if -90 <= a <= 90 and -180 <= b <= 180 and not (a == 0 and b == 0):
                lat, lng = a, b
                break
    log("gps:", url, "->", lat, lng, name)
    cache[url] = {"lat": lat, "lng": lng, "name": name}
    return cache[url]


def locate(info, cache):
    """Deepest area first, then parents. Returns (lat, lng, area name, approx) or None."""
    for i, a in enumerate(reversed(info["areas"])):
        ai = area_info(a["url"], cache)
        if ai["lat"] is not None:
            return ai["lat"], ai["lng"], ai["name"] or a["name"], i > 0
    return None


def process_photo(url, cache):
    """Returns (entry, None) for a usable photo, or (None, reason).
    Reasons starting with 'filtered' are permanent; 'unreadable' may be a
    layout change or a transient problem, so callers should retry later.
    Network errors (urllib.error.URLError) propagate."""
    info = parse_photo_page(url)
    why = skip_reason(info)
    if why:
        return None, "filtered: " + why
    if not info["imageUrl"] or not info["areas"]:
        return None, "unreadable: no image URL or area found"
    loc = locate(info, cache)
    if not loc:
        return None, "unreadable: no GPS found on the area or its parents"
    lat, lng, area_name, approx = loc
    return {
        "id": photo_id(url),
        "photoUrl": info["photoUrl"],
        "imageUrl": info["imageUrl"],
        "title": info["title"],
        "breadcrumb": info["breadcrumb"],
        "coordArea": area_name,
        "approx": approx,
        "lat": lat,
        "lng": lng,
    }, None
