"""Builds common/birdinfo.json and photos/ from a bird list and its photos.

Run it on a computer with internet (not on a Pi), from the bbbb-display folder:

    python3 -m venv ~/bbbb-tools && ~/bbbb-tools/bin/pip install pillow      (first time only)
    ~/bbbb-tools/bin/python tools/build_birdinfo.py "/path/to/04 Bird data"

The bird data folder holds:
    bristol_birds_with_q.txt   one bird per line: Scientific name_BirdNET name_Wikidata id
    bird_pics_wikipedia/       a photo of each bird, named by its Wikidata id (Q25334.jpg)
    photo_sources.txt          (optional) the right Commons photo for birds it gets wrong, one per
                               line: Wikidata id, then a link to the photo's Commons page, e.g.
                               Q25348 https://commons.wikimedia.org/wiki/File:Male_mallard.jpg

For each bird it:
    - looks up its conservation status, order and family on Wikidata
    - gets the opening text and link of its Wikipedia article
    - finds which Wikimedia Commons file the photo is, for its credit
    - shrinks the photo into photos/ (or downloads one if there isn't a photo)
Anything else already in birdinfo.json (short names, poem words, tile facts) is kept.
Photos it can't match to a Commons file are listed at the end: find the right one
and add it to photo_sources.txt. A bird in photo_sources.txt gets that photo's credit,
and that photo too if it isn't the one in bird_pics_wikipedia/.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html import unescape
from io import BytesIO

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                  # the bbbb-display folder
BIRD_INFO = os.path.join(ROOT, "common", "birdinfo.json")
PHOTOS = os.path.join(ROOT, "photos")

LIST_FILE = "bristol_birds_with_q.txt"
PHOTO_FOLDER = "bird_pics_wikipedia"
SOURCES_FILE = "photo_sources.txt"
PHOTO_SIZE = 800                    # longest side of the photos kept, in pixels
MATCH_LIMIT = 14                    # how different a Commons photo may look and still be a match (0-255)
USER_AGENT = "bbbb-display-builder/1.0 (https://github.com/kwmc-chris/bbbb-display)"   # Wikimedia asks for this
RANK_FAMILY, RANK_ORDER = "Q35409", "Q36602"                  # Wikidata ids for "family", "order"

README = ("One entry per bird, under BirdNET-Pi's name for it (also found by sci, its scientific "
          "name, or a list of them). Made by tools/build_birdinfo.py, which keeps anything added "
          "by hand. short_name, search: the simple display's name and poem words. habitat to "
          "family_name: the full display's browse tiles. conservation, order, family: Wikidata. "
          "description, wiki_url: Wikipedia. photo: the file in photos/, photo_credit: its credit.")


# --- Web ---

def get(url):
    """The contents of a web address. If the site says "too many requests" (or fails),
    wait and try again, up to 6 times, waiting longer each time."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.5)                                  # be polite between requests
                return r.read()
        except Exception as e:
            if attempt == 5:
                raise
            wait = 5 * 2 ** attempt                              # 5, 10, 20, 40, 80 seconds
            retry_after = getattr(e, "headers", None) and e.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = max(wait, int(retry_after))
            print(f"  {e} - trying again in {wait} s")
            time.sleep(wait)


def get_json(url, **params):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return json.loads(get(url))


def in_groups(items, size=50):
    """items split into lists of up to size (50 is the most the Wikimedia APIs take at once)."""
    items = list(items)
    return [items[i:i + size] for i in range(0, len(items), size)]


# --- Wikidata ---

_entities = {}


def entities(qids):
    """Wikidata items by id, fetched 50 at a time (and remembered)."""
    qids = list(qids)
    wanted = [q for q in set(qids) if q and q not in _entities]
    for group in in_groups(wanted):
        data = get_json("https://www.wikidata.org/w/api.php", action="wbgetentities", format="json",
                        props="claims|labels|sitelinks", languages="en", sitefilter="enwiki",
                        ids="|".join(group))
        _entities.update(data.get("entities", {}))
    return {q: _entities.get(q, {}) for q in qids if q}


def claims(item, prop):
    """All values of a Wikidata property: item ids or text."""
    out = []
    for c in item.get("claims", {}).get(prop, []):
        value = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict):
            value = value.get("id")
        if value:
            out.append(value)
    return out


def label(item):
    return item.get("labels", {}).get("en", {}).get("value", "")


def taxonomy(qids):
    """{qid: {"order", "family"}}, by walking up each bird's parent taxa."""
    found = {q: {} for q in qids}
    current = {q: q for q in qids}               # bird -> the taxon reached so far
    for _ in range(12):
        items = entities(current.values())
        parents = {}
        for bird, taxon in current.items():
            parent = (claims(items.get(taxon, {}), "P171") or [None])[0]
            if parent:
                parents[bird] = parent
        parent_items = entities(parents.values())
        for bird, parent in list(parents.items()):
            item = parent_items.get(parent, {})
            rank = (claims(item, "P105") or [None])[0]
            name = (claims(item, "P225") or [None])[0]          # scientific name
            if rank == RANK_FAMILY:
                found[bird]["family"] = name
            elif rank == RANK_ORDER:
                found[bird]["order"] = name
                del parents[bird]                                # done once the order is found
        current = parents
        if not current:
            break
    return found


# --- Wikipedia and Commons ---

def wikipedia(titles):
    """{title: {"description", "wiki_url", "image"}} for Wikipedia articles, 20 at a time
    (the most it gives opening text for at once). Missing articles are left out."""
    out = {}
    for group in in_groups(set(titles), 20):
        data = get_json("https://en.wikipedia.org/w/api.php", action="query", format="json", redirects=1,
                        prop="extracts|pageimages", exintro=1, explaintext=1, exlimit=20, piprop="name",
                        titles="|".join(group))
        query = data.get("query", {})
        # The title asked for -> the article's title (after spelling fixes and redirects)
        moved = {m["from"]: m["to"] for m in query.get("normalized", []) + query.get("redirects", [])}
        pages = {p.get("title"): p for p in query.get("pages", {}).values()}
        for title in group:
            final = title
            while final in moved:
                final = moved[final]
            page = pages.get(final, {})
            if "missing" in page or not page.get("pageid"):
                print(f"  Wikipedia: no article called {title}")
                continue
            text = (page.get("extract") or "").strip()
            out[title] = {"description": text.split("\n")[0].strip(),       # the first paragraph
                          "wiki_url": f"https://en.wikipedia.org/?curid={page['pageid']}",
                          "image": page.get("pageimage", "")}
    return out


def commons(files):
    """{file name: {"thumb", "credit", "big"}} for Commons files, 50 at a time."""
    out = {}
    for group in in_groups(set(files)):
        for width, key in ((64, "thumb"), (PHOTO_SIZE, "big")):
            data = get_json("https://commons.wikimedia.org/w/api.php", action="query", format="json",
                            prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=width,
                            titles="|".join("File:" + f for f in group))
            pages = data.get("query", {}).get("pages", {}).values()
            names = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
            for page in pages:
                info = (page.get("imageinfo") or [{}])[0]
                name = names.get(page.get("title"), page.get("title", ""))[len("File:"):]
                entry = out.setdefault(name, {})
                entry[key] = info.get("thumburl") or info.get("url")
                entry.setdefault("credit", credit(info.get("extmetadata", {})))
    return out


def credit(meta):
    """"Artist / Wikimedia Commons (licence)" from Commons' file details."""
    def text(key):                                  # the value without HTML tags
        raw = meta.get(key, {}).get("value", "")
        return " ".join(unescape(re.sub(r"<[^>]+>", "", raw)).split())
    artist, licence = text("Artist"), text("LicenseShortName")
    return (f"{artist} / Wikimedia Commons" if artist else "Wikimedia Commons") + (f" ({licence})" if licence else "")


# --- Photos ---

def fingerprint(img):
    """A tiny greyscale copy of a picture, for comparing two photos."""
    return list(ImageOps.exif_transpose(img).convert("L").resize((16, 16)).getdata())


def difference(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def save_photo(img, path):
    """Shrink a photo to PHOTO_SIZE on its longest side and save it as a JPEG."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((PHOTO_SIZE, PHOTO_SIZE))
    img.save(path, "JPEG", quality=85, optimize=True)


# --- Main ---

def as_json(birds):
    """birdinfo.json's text: one bird after another, one field per line."""
    blocks = []
    for name, entry in birds.items():
        if not isinstance(entry, dict):
            blocks.append(f"  {json.dumps(name)}: {json.dumps(entry, ensure_ascii=False)}")
            continue
        fields = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in entry.items())
        blocks.append(f"  {json.dumps(name)}: {{\n{fields}\n  }}")
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def read_list(path):
    """[(scientific name, BirdNET name, Wikidata id)] from the bird list."""
    birds = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("_")
            if len(parts) == 3:
                birds.append(tuple(parts))
            elif line.strip():
                print(f"Skipped a line I can't read: {line.strip()}")
    return birds


def read_sources(path):
    """{Wikidata id: Commons file name} from photo_sources.txt, or {} if there isn't one."""
    sources = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.split(None, 1)
                if len(parts) == 2 and "File:" in parts[1]:
                    name = urllib.parse.unquote(parts[1].strip().split("File:", 1)[1])
                    sources[parts[0]] = name.replace("_", " ")
    return sources


def old_entry(old, name, sci):
    """The bird's entry already in birdinfo.json, by name or scientific name, or {}."""
    if name in old:
        return old[name]
    for entry in old.values():
        names = entry.get("sci") if isinstance(entry, dict) else None
        if sci in ([names] if isinstance(names, str) else names or []):
            return entry
    return {}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    folder = sys.argv[1]
    birds = read_list(os.path.join(folder, LIST_FILE))
    sources = read_sources(os.path.join(folder, SOURCES_FILE))
    print(f"{len(birds)} birds in {LIST_FILE}, {len(sources)} in {SOURCES_FILE}")
    with open(BIRD_INFO, encoding="utf-8") as f:
        old = json.load(f)
    old.pop("_readme", None)
    os.makedirs(PHOTOS, exist_ok=True)

    # Wikidata: each bird's item, its taxonomy, and the labels of the conservation statuses
    print("Wikidata...")
    items = entities(q for _, _, q in birds)
    taxa = taxonomy([q for _, _, q in birds])
    statuses = entities(s for item in items.values() for s in claims(item, "P141")[:1])

    # Wikipedia: opening text, link and main photo of each bird's article
    print("Wikipedia...")
    titles = {qid: items[qid].get("sitelinks", {}).get("enwiki", {}).get("title") or sci for sci, _, qid in birds}
    articles = wikipedia(titles.values())
    pages = {qid: articles.get(title, {}) for qid, title in titles.items()}

    # Commons: every photo a bird might have (Wikidata's, and the Wikipedia article's)
    print("Commons...")
    options = {qid: [sources[qid]] if qid in sources else
               list(dict.fromkeys(claims(items[qid], "P18") + [pages[qid].get("image")]))
               for _, _, qid in birds}
    files = commons(f for opts in options.values() for f in opts if f)

    # Each bird: match or download its photo, then write its entry
    print("Photos...")
    out, unmatched = {"_readme": README}, []
    for sci, name, qid in birds:
        mine = os.path.join(folder, PHOTO_FOLDER, qid + ".jpg")
        photo, photo_credit = qid + ".jpg", None
        if os.path.exists(mine) and qid in sources:
            # photo_sources.txt: this Commons photo and its credit (downloaded if it isn't mine)
            f = sources[qid]
            if f not in files:
                print(f"  {SOURCES_FILE}: can't find {f} on Commons")
                save_photo(Image.open(mine), os.path.join(PHOTOS, photo))
            else:
                score = difference(fingerprint(Image.open(mine)), fingerprint(Image.open(BytesIO(get(files[f]["thumb"])))))
                if score <= MATCH_LIMIT:
                    save_photo(Image.open(mine), os.path.join(PHOTOS, photo))
                else:
                    save_photo(Image.open(BytesIO(get(files[f]["big"]))), os.path.join(PHOTOS, photo))
                    print(f"  {name}: using {f} from {SOURCES_FILE}")
                photo_credit = files[f]["credit"]
        elif os.path.exists(mine):
            img = Image.open(mine)
            mine_print = fingerprint(img)
            best = None
            for f in options[qid]:
                if f in files and files[f].get("thumb"):
                    score = difference(mine_print, fingerprint(Image.open(BytesIO(get(files[f]["thumb"])))))
                    if best is None or score < best[0]:
                        best = (score, f)
            if best and best[0] <= MATCH_LIMIT:
                photo_credit = files[best[1]]["credit"]
            else:
                unmatched.append(f"{name} ({qid}.jpg)" + (f" - closest {best[1]}" if best else ""))
            save_photo(img, os.path.join(PHOTOS, photo))
        else:
            f = next((f for f in options[qid] if f in files and files[f].get("big")), None)
            if f:
                save_photo(Image.open(BytesIO(get(files[f]["big"]))), os.path.join(PHOTOS, photo))
                photo_credit = files[f]["credit"]
                print(f"  Downloaded a photo for {name}: {f}")
            else:
                photo = None
                print(f"  No photo for {name}")

        # Bird list and web facts, then anything added by hand
        entry = {"sci": sci, "qid": qid}
        entry.update(old_entry(old, name, sci))
        others = entry["sci"] if isinstance(entry["sci"], list) else [entry["sci"]]
        others = [s for s in others if s != sci]               # other scientific names kept, list's first
        entry["sci"] = [sci] + others if others else sci
        entry["qid"] = qid
        status = claims(items[qid], "P141")[:1]
        if status:
            entry["conservation"] = label(statuses.get(status[0], {})).title()
        entry.update({k: v for k, v in taxa.get(qid, {}).items() if v})
        page = pages[qid]
        entry["description"] = page.get("description", "")
        entry["wiki_url"] = page.get("wiki_url", "")
        entry["photo"] = photo
        entry["photo_credit"] = photo_credit or entry.get("photo_credit") or "Wikimedia Commons"   # keeps a credit added by hand
        out[name] = {k: v for k, v in entry.items() if v not in (None, "", [])}

    # Keep hand-made entries for birds that aren't in the list
    for name, entry in old.items():
        if name not in out and not any(old_entry({name: entry}, n, s) for s, n, _ in birds):
            out[name] = entry

    with open(BIRD_INFO, "w", encoding="utf-8") as f:
        f.write(as_json(out))
    print(f"Wrote {len(out) - 1} birds to common/birdinfo.json and their photos to photos/")
    if unmatched:
        print(f"\n{len(unmatched)} photos didn't match a Commons file, so they kept their old credit "
              f"(or just \"Wikimedia Commons\"). Find the right one and add it to {SOURCES_FILE}:")
        for line in unmatched:
            print("  " + line)


if __name__ == "__main__":
    main()
