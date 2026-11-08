"""A photo of a bird, with its credit: your own photo from birds/ (e.g.
birds/European Robin.jpg or birds/Robin.jpg), otherwise the bird's Wikipedia
photo. Downloads are kept in cache/photos/.
"""

import os
import re
import urllib.parse

from common import CACHE, ROOT, web

OWN_PHOTOS = os.path.join(ROOT, "birds")
WIKI_WIDTHS = (960, 1280, 500)     # photo widths to try


def get_photo(com_name, sci_name=None, *other_names):
    """(path, credit), or (None, None). Credit is None for your own photos."""
    own = own_photo(com_name, *other_names)
    if own:
        return own, None

    # Downloaded before
    folder = os.path.join(CACHE, "photos")
    credits_file = os.path.join(folder, "credits.json")
    credits = web.load_json(credits_file)
    name = web.slug(com_name)
    path = os.path.join(folder, name + ".jpg")
    if credits.get(name) and os.path.exists(path):
        return path, credits[name]

    # Download from Wikipedia
    urls, credit = wikipedia_photo(com_name, sci_name)
    for url in urls:
        try:
            data = web.get(url)
        except Exception:
            continue
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        credits[name] = credit
        web.save_json(credits_file, credits)
        return path, credit
    return None, None


def own_photo(*names):
    """Your photo in birds/ named after the bird, or None."""
    if not os.path.isdir(OWN_PHOTOS):
        return None
    wanted = {n.lower().replace(" ", sep) for n in names if n for sep in (" ", "_", "-")}
    for f in sorted(os.listdir(OWN_PHOTOS)):
        stem, ext = os.path.splitext(f)
        if stem.lower() in wanted and ext.lower() in (".jpg", ".jpeg", ".png"):
            return os.path.join(OWN_PHOTOS, f)
    return None


def wikipedia_photo(com_name, sci_name):
    """(addresses to try, credit) for the main photo of the bird's Wikipedia article."""
    page = web.wiki_summary(com_name, sci_name) or {}
    thumb = (page.get("thumbnail") or {}).get("source", "")
    if not thumb:
        return [], None
    urls = [re.sub(r"/\d+px-", f"/{w}px-", thumb) for w in WIKI_WIDTHS] if "/thumb/" in thumb else []
    urls.append(thumb)
    # Address form: .../thumb/a/ab/File_name.jpg/960px-File_name.jpg
    parts = urllib.parse.unquote(thumb).split("/")
    filename = parts[-2] if "/thumb/" in thumb else parts[-1]
    return urls, web.commons_credit(filename)
