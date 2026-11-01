"""A photo of a bird, with its credit. Tried in order:
    1. your own photo in the birds/ folder, named after the bird
       (e.g. birds/European Robin.jpg or birds/Robin.jpg)
    2. Flickr, if BirdNET-Pi has a Flickr key (as BirdNET-Pi itself does)
    3. the bird's Wikipedia photo
Downloads are kept in cache/photos/ so each bird is fetched once.
"""

import os
import re
import urllib.parse

from common import CACHE, ROOT, birdnet, web

OWN_PHOTOS = os.path.join(ROOT, "birds")
WIKI_WIDTHS = (960, 1280, 500)     # Wikimedia only serves standard widths


def get_photo(com_name, sci_name=None, *other_names):
    """(path, credit), or (None, None) if there's no photo. Credit is None for your own."""
    own = own_photo(com_name, *other_names)
    if own:
        return own, None

    folder = os.path.join(CACHE, "photos")
    credits_file = os.path.join(folder, "credits.json")
    credits = web.load_json(credits_file)
    name = web.slug(com_name)
    path = os.path.join(folder, name + ".jpg")
    if credits.get(name) and os.path.exists(path):
        return path, credits[name]

    os.makedirs(folder, exist_ok=True)
    for find in (flickr_photo, wikipedia_photo):
        try:
            urls, credit = find(com_name, sci_name)
        except Exception:
            continue
        for url in urls:
            try:
                data = web.get(url)
            except Exception:
                continue
            with open(path, "wb") as f:
                f.write(data)
            credits[name] = credit
            web.save_json(credits_file, credits)
            return path, credit
    return None, None


def own_photo(*names):
    if not os.path.isdir(OWN_PHOTOS):
        return None
    wanted = {n.lower().replace(" ", sep) for n in names if n for sep in (" ", "_", "-")}
    for f in sorted(os.listdir(OWN_PHOTOS)):
        stem, ext = os.path.splitext(f)
        if stem.lower() in wanted and ext.lower() in (".jpg", ".jpeg", ".png"):
            return os.path.join(OWN_PHOTOS, f)
    return None


def flickr_photo(com_name, sci_name):
    """([url], credit) from Flickr, only if BirdNET-Pi has a Flickr key."""
    conf = birdnet.config()
    key = conf.get("FLICKR_API_KEY")
    if not key or conf.get("IMAGE_PROVIDER", "").upper() == "WIKIPEDIA":
        return [], None
    api = "https://api.flickr.com/services/rest/?format=json&nojsoncallback=1&api_key=" + key
    user = ""
    if conf.get("FLICKR_FILTER_EMAIL"):          # only one person's photos, as BirdNET-Pi does
        data = web.get_json(api + "&method=flickr.people.findByEmail&find_email="
                            + urllib.parse.quote(conf["FLICKR_FILTER_EMAIL"]))
        user = "&user_id=" + data["user"]["nsid"]
    for term in filter(None, (com_name, sci_name)):
        photos = web.get_json(api + "&method=flickr.photos.search&sort=relevance&media=photos"
                              "&content_type=1&per_page=5&extras=owner_name" + user
                              + "&text=" + urllib.parse.quote(term))["photos"]["photo"]
        if photos:
            p = photos[0]
            url = f"https://live.staticflickr.com/{p['server']}/{p['id']}_{p['secret']}_b.jpg"
            return [url], f"© {p.get('ownername', 'Flickr')} / Flickr"
    return [], None


def wikipedia_photo(com_name, sci_name):
    """(urls to try, credit) for the main photo of the bird's Wikipedia article."""
    page = web.wiki_summary(com_name, sci_name) or {}
    thumb = (page.get("thumbnail") or {}).get("source", "")
    if not thumb:
        return [], None
    urls = [re.sub(r"/\d+px-", f"/{w}px-", thumb) for w in WIKI_WIDTHS] if "/thumb/" in thumb else []
    urls.append(thumb)
    # Thumbnail address: .../thumb/a/ab/File_name.jpg/960px-File_name.jpg
    parts = urllib.parse.unquote(thumb).split("/")
    filename = parts[-2] if "/thumb/" in thumb else parts[-1]
    return urls, web.commons_credit(filename)
