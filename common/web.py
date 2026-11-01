"""Web lookups: Wikipedia, Wikimedia Commons, and saving results."""

import json
import os
import re
import urllib.parse
import urllib.request
from html import unescape

USER_AGENT = "bbbb-display/1.0 (Raspberry Pi bird display)"   # some sites block Python's default
TIMEOUT = 15            # seconds per request
WIKI_LANG = "en"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def get_json(url):
    return json.loads(get(url).decode("utf-8", errors="replace"))


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {} if default is None else default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def slug(name):
    """Safe file name: "Cetti's Warbler" -> "Cettis_Warbler"."""
    return re.sub(r"\W+", "_", name.replace("'", "").replace("’", "")).strip("_")


def strip_tags(text):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


_summaries = {}


def wiki_summary(*titles):
    """Wikipedia's summary of the first title that has an article, or None.
    Has "extract" (opening text), "pageid" and "thumbnail" (main photo)."""
    for title in filter(None, titles):
        if title not in _summaries:
            try:
                data = get_json(f"https://{WIKI_LANG}.wikipedia.org/api/rest_v1/page/summary/"
                                + urllib.parse.quote(title.replace(" ", "_")))
            except Exception:
                continue                     # not found, or offline
            _summaries[title] = data if data.get("type") == "standard" else None
        if _summaries[title]:
            return _summaries[title]
    return None


def commons_credit(filename):
    """"Artist / Wikimedia Commons (licence)" for a file on Wikimedia Commons."""
    try:
        data = get_json("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                        "&prop=imageinfo&iiprop=extmetadata&titles=File:"
                        + urllib.parse.quote(filename))
        meta = next(iter(data["query"]["pages"].values()))["imageinfo"][0]["extmetadata"]
        artist = strip_tags(meta.get("Artist", {}).get("value"))
        licence = strip_tags(meta.get("LicenseShortName", {}).get("value"))
        if artist:
            return f"{artist} / Wikimedia Commons" + (f" ({licence})" if licence else "")
    except Exception:
        pass
    return "Wikimedia Commons"
