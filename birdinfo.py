#!/usr/bin/env python3
"""
birdinfo.py - bird information for bbbb-display.py.

    get_description(name, sci)  Wikipedia's opening text, cut to N sentences
    get_image(name, sci)        photo (Flickr if BirdNET-Pi has a key, else Wikipedia) + credit
    get_details(name, sci)      browse tile facts: birdfacts.json, else Wikidata

Results are saved next to this file, so each bird is looked up once.

Test:  python3 birdinfo.py "European Robin" "Erithacus rubecula" [--refresh]

Sections: 1 Settings, 2 Imports, 3 Helpers, 4 Descriptions, 5 Photos,
          6 Tile facts, 7 Test
"""

# =============================================================================
# 1. SETTINGS
# =============================================================================

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FACTS_FILE = os.path.join(SCRIPT_DIR, "birdfacts.json")                   # your tile facts
DESC_CACHE = os.path.join(SCRIPT_DIR, "birdinfo_descriptions.json")       # saved Wikipedia text
WIKIDATA_CACHE = os.path.join(SCRIPT_DIR, "birdinfo_wikidata.json")
IMAGE_DIR = os.path.join(SCRIPT_DIR, "bird_photos")
CREDITS_FILE = os.path.join(IMAGE_DIR, "credits.json")

# BirdNET-Pi's settings (for its Flickr key); first one found is used
CONF_PATHS = ["/etc/birdnet/birdnet.conf", os.path.expanduser("~/BirdNET-Pi/birdnet.conf")]

DESCRIPTION_MAX_CHARS = 170      # default length (live screen)
WIKI_LANG = "en"                 # Wikipedia language
USER_AGENT = "birdnet-inky-display/1.0 (personal Raspberry Pi bird display)"
TIMEOUT = 10                     # seconds per web request
WIKI_SIZES = (960, 1280, 500)    # photo widths to try (Wikimedia standard sizes only)

# =============================================================================
# 2. IMPORTS
# =============================================================================

import json
import re
import sys
import urllib.parse
import urllib.request
from html import unescape

RANK_FAMILY, RANK_ORDER = "Q35409", "Q36602"     # Wikidata IDs for these ranks

# =============================================================================
# 3. HELPERS
# =============================================================================

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def _get_json(url):
    return json.loads(_get(url))


def _download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)


def _clean(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def _strip_tags(text):
    return _clean(re.sub(r"<[^>]+>", "", text or ""))


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def first_sentences(text, sentences=1, max_chars=DESCRIPTION_MAX_CHARS):
    """First N sentences, cut to max_chars with "…".
    A break needs . ! or ? then a capital, and 30+ characters before it
    (so "St." etc. don't count)."""
    text = _clean(text)
    parts, current = [], ""
    for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
        current = f"{current} {piece}".strip()
        if len(current) >= 30:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    result = " ".join(parts[:sentences])
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return result


def slug(com_name):
    """Safe file name: "Cetti's Warbler" -> "Cettis_Warbler"."""
    return re.sub(r"\s+", "_", com_name.replace("'", "").replace("’", "").strip())

# =============================================================================
# 4. DESCRIPTIONS  (Wikipedia page summary: opening paragraph + main photo)
# =============================================================================

_summaries = {}                  # fetched this run


def wiki_summary(com_name, sci_name=None):
    """Wikipedia summary dict (tries common then scientific name), or None."""
    for title in filter(None, (com_name, sci_name)):
        if title in _summaries:
            return _summaries[title]
        try:
            data = _get_json(f"https://{WIKI_LANG}.wikipedia.org/api/rest_v1/page/summary/"
                             + urllib.parse.quote(title.replace(" ", "_")))
        except Exception:
            continue
        if data.get("type") == "standard":       # not a disambiguation page
            _summaries[title] = data
            return data
    return None


def get_description(com_name, sci_name=None, refresh=False, sentences=1,
                    max_chars=DESCRIPTION_MAX_CHARS):
    """Opening text of the bird's Wikipedia article, cut to `sentences`
    sentences and max_chars. The full paragraph is saved; cutting happens here."""
    cache = _load_json(DESC_CACHE)
    text = None if refresh else cache.get(com_name)
    if not text:
        data = wiki_summary(com_name, sci_name)
        text = (data or {}).get("extract")
        if not text:
            return None
        cache[com_name] = text
        _save_json(DESC_CACHE, cache)
    return first_sentences(text, sentences, max_chars)

# =============================================================================
# 5. PHOTOS  (same sources as BirdNET-Pi: Flickr if keyed, else Wikipedia)
# =============================================================================

def birdnet_config():
    """BirdNET-Pi's settings file as a dict."""
    conf = {}
    for path in CONF_PATHS:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        conf[key.strip()] = value.strip().strip('"').strip("'")
            break
        except OSError:
            continue
    return conf


def _flickr_photo(com_name, sci_name, conf):
    """([url], credit) from Flickr, or (None, None)."""
    key = conf.get("FLICKR_API_KEY")
    if not key:
        return None, None
    api = "https://api.flickr.com/services/rest/?format=json&nojsoncallback=1&api_key=" + key

    user = ""                    # limit to one account if BirdNET-Pi does
    if conf.get("FLICKR_FILTER_EMAIL"):
        try:
            data = _get_json(api + "&method=flickr.people.findByEmail&find_email="
                             + urllib.parse.quote(conf["FLICKR_FILTER_EMAIL"]))
            user = "&user_id=" + data["user"]["nsid"]
        except Exception:
            pass

    for term in filter(None, (com_name, sci_name)):
        try:
            photos = _get_json(api + "&method=flickr.photos.search&sort=relevance"
                               "&media=photos&content_type=1&per_page=5&extras=owner_name"
                               + user + "&text=" + urllib.parse.quote(term))["photos"]["photo"]
        except Exception:
            continue
        if photos:
            ph = photos[0]
            url = f"https://live.staticflickr.com/{ph['server']}/{ph['id']}_{ph['secret']}_b.jpg"
            return [url], f"© {ph.get('ownername', 'Flickr')} / Flickr"
    return None, None


def _wiki_photo(com_name, sci_name):
    """(urls to try, credit) for the article's main photo."""
    data = wiki_summary(com_name, sci_name)
    if not data:
        return None, None
    thumb = (data.get("thumbnail") or {}).get("source", "")
    original = (data.get("originalimage") or {}).get("source", "")
    urls = []
    if "/thumb/" in thumb:       # swap in each preferred width
        urls += [re.sub(r"/\d+px-", f"/{w}px-", thumb) for w in WIKI_SIZES]
    urls += [u for u in (original, thumb) if u]
    return (urls, _wikimedia_credit(urls[0])) if urls else (None, None)


def _wikimedia_credit(img_url):
    """"Artist / Wikimedia Commons (licence)" for a Wikimedia photo."""
    try:
        parts = urllib.parse.unquote(img_url).split("/")
        filename = parts[-2] if "/thumb/" in img_url else parts[-1]
        data = _get_json("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                         "&prop=imageinfo&iiprop=extmetadata&titles=File:"
                         + urllib.parse.quote(filename))
        meta = next(iter(data["query"]["pages"].values()))["imageinfo"][0]["extmetadata"]
        artist = _strip_tags(meta.get("Artist", {}).get("value"))
        licence = _strip_tags(meta.get("LicenseShortName", {}).get("value"))
        if artist:
            return f"{artist} / Wikimedia Commons" + (f" ({licence})" if licence else "")
    except Exception:
        pass
    return "Wikimedia Commons"


def get_image(com_name, sci_name=None, refresh=False):
    """(photo path, credit), or (None, None). Saved photos are reused."""
    credits = _load_json(CREDITS_FILE)
    name = slug(com_name)
    path = os.path.join(IMAGE_DIR, name + ".jpg")
    if not refresh and credits.get(name) and os.path.exists(path):
        return path, credits[name]

    conf = birdnet_config()
    sources = []
    if conf.get("IMAGE_PROVIDER", "").upper() != "WIKIPEDIA":
        sources.append(("Flickr", lambda: _flickr_photo(com_name, sci_name, conf)))
    sources.append(("Wikipedia", lambda: _wiki_photo(com_name, sci_name)))

    os.makedirs(IMAGE_DIR, exist_ok=True)
    for source, find in sources:
        try:
            urls, credit = find()
        except Exception:
            urls, credit = None, None
        for url in urls or []:
            try:
                _download(url, path)
            except Exception as e:
                print(f"Photo download from {source} failed: {e}")
                continue
            credits[name] = credit
            _save_json(CREDITS_FILE, credits)
            return path, credit
    return None, None

# =============================================================================
# 6. TILE FACTS
#    source "file":     birdfacts.json (all five tiles)
#    source "wikidata": global conservation status, order, family
# =============================================================================

def facts_from_file(com_name, sci_name=None):
    """Entry from birdfacts.json by scientific name, then "name". Re-read each time."""
    facts = _load_json(FACTS_FILE)
    entry = facts.get(sci_name or "")
    if not entry:
        wanted = com_name.lower()
        entry = next((v for k, v in facts.items()
                      if isinstance(v, dict) and v.get("name", "").lower() == wanted), None)
    if not entry:
        return None
    out = {k: v for k, v in entry.items() if k != "name"}
    out["source"] = "file"
    return out


# Wikidata claims used: P141 IUCN status, P171 parent taxon, P105 rank, P225 name

def _wd_entity(qid):
    data = _get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
                     "&props=claims|labels&languages=en&ids=" + qid)
    return data["entities"][qid]


def _claim_id(entity, prop):
    try:
        return entity["claims"][prop][0]["mainsnak"]["datavalue"]["value"]["id"]
    except (KeyError, IndexError, TypeError):
        return None


def _claim_str(entity, prop):
    try:
        return entity["claims"][prop][0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None


def facts_from_wikidata(com_name, sci_name=None, refresh=False):
    """{source, conservation, order, family} from Wikidata, or {}."""
    cache = _load_json(WIKIDATA_CACHE)
    if not refresh and cache.get(com_name):
        return cache[com_name]

    # Find the Wikidata item linked to the Wikipedia article
    qid = None
    for title in filter(None, (sci_name, com_name)):
        try:
            data = _get_json(f"https://{WIKI_LANG}.wikipedia.org/w/api.php?action=query"
                             "&format=json&prop=pageprops&ppprop=wikibase_item&redirects=1"
                             "&titles=" + urllib.parse.quote(title))
            page = next(iter(data["query"]["pages"].values()))
            qid = page.get("pageprops", {}).get("wikibase_item")
        except Exception:
            qid = None
        if qid:
            break
    if not qid:
        return {}

    out = {"source": "wikidata"}
    try:
        entity = _wd_entity(qid)
        status_id = _claim_id(entity, "P141")
        if status_id:
            label = _wd_entity(status_id).get("labels", {}).get("en", {}).get("value", "")
            if label:
                out["conservation"] = label.title()
        # Climb parent taxa to the family and order
        current = entity
        for _ in range(8):
            parent = _claim_id(current, "P171")
            if not parent:
                break
            current = _wd_entity(parent)
            rank = _claim_id(current, "P105")
            if rank == RANK_FAMILY:
                out["family"] = _claim_str(current, "P225")
            elif rank == RANK_ORDER:
                out["order"] = _claim_str(current, "P225")
                break
    except Exception as e:
        print(f"Wikidata lookup failed: {e}")

    if len(out) > 1:             # don't save empty results
        cache[com_name] = out
        _save_json(WIKIDATA_CACHE, cache)
    return out


def get_details(com_name, sci_name=None, refresh=False):
    """Tile facts dict (may be empty)."""
    return (facts_from_file(com_name, sci_name)
            or facts_from_wikidata(com_name, sci_name, refresh) or {})

# =============================================================================
# 7. TEST
# =============================================================================

if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        raise SystemExit('Usage: python3 birdinfo.py "Common Name" ["Scientific name"] [--refresh]')
    com = names[0]
    sci = names[1] if len(names) > 1 else None
    refresh = "--refresh" in sys.argv

    print("Description:", get_description(com, sci, refresh, sentences=3, max_chars=600)
          or "none found")
    details = get_details(com, sci, refresh)
    print("Details:", json.dumps(details, indent=2) if details else "none found")
    if details.get("source") == "wikidata":
        print(f"(Not in birdfacts.json - add '{sci or com}' to fill all the tiles.)")
    conf = birdnet_config()
    print("BirdNET-Pi settings:", "found" if conf else "not found",
          "| Flickr key:", "yes" if conf.get("FLICKR_API_KEY") else "no")
    path, credit = get_image(com, sci, refresh)
    print(f"Photo: {path} ({credit})" if path else "No photo found.")
