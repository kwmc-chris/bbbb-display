"""Facts about a bird for the full display; lookups are saved in cache/.

    description(name, sci)   opening text of its Wikipedia article
    wiki_link(name, sci)     short link to the article (for the QR code)
    details(name, sci)       tile facts: birdfacts.json, else Wikidata
"""

import os
import re
import urllib.parse

from common import CACHE, web

HERE = os.path.dirname(os.path.abspath(__file__))
FACTS_FILE = os.path.join(HERE, "birdfacts.json")         # your facts for the tiles
ARTICLES = os.path.join(CACHE, "wikipedia.json")
WIKIDATA = os.path.join(CACHE, "wikidata.json")
RANK_FAMILY, RANK_ORDER = "Q35409", "Q36602"             # Wikidata ids


# --- Wikipedia ---

def article(com_name, sci_name=None):
    """{"text", "url"} for the bird's Wikipedia article, or {}."""
    saved = web.load_json(ARTICLES)
    if com_name not in saved:
        page = web.wiki_summary(com_name, sci_name)
        if not (page and page.get("extract")):
            return {}
        url = f"https://{web.WIKI_LANG}.wikipedia.org/?curid={page['pageid']}" \
            if page.get("pageid") else None
        saved[com_name] = {"text": page["extract"], "url": url}
        web.save_json(ARTICLES, saved)
    return saved[com_name]


def description(com_name, sci_name=None, sentences=1, max_chars=170):
    """Opening text of the article, cut to length, or None."""
    text = article(com_name, sci_name).get("text")
    return first_sentences(text, sentences, max_chars) if text else None


def wiki_link(com_name, sci_name=None):
    """Short link to the article, or None."""
    return article(com_name, sci_name).get("url")


def first_sentences(text, sentences, max_chars):
    """The first few sentences, cut to max_chars with "…".
    A sentence must be at least 30 characters long."""
    parts, current = [], ""
    for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z])", re.sub(r"\s+", " ", text).strip()):
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


# --- Tile facts ---

def details(com_name, sci_name=None):
    """Tile facts: {"source": "file", habitat, food, nesting, behavior, uk_status...}
    from birdfacts.json, else {"source": "wikidata", conservation, order, family}, or {}."""
    return from_file(com_name, sci_name) or from_wikidata(com_name, sci_name) or {}


def from_file(com_name, sci_name=None):
    """The bird's entry in birdfacts.json, by scientific name or "name", or None."""
    facts = web.load_json(FACTS_FILE)
    entry = facts.get(sci_name or "")
    if not entry:
        entry = next((v for v in facts.values() if isinstance(v, dict)
                      and v.get("name", "").lower() == com_name.lower()), None)
    if not entry:
        return None
    return dict({k: v for k, v in entry.items() if k != "name"}, source="file")


def from_wikidata(com_name, sci_name=None):
    """{"source": "wikidata", conservation, order, family} from Wikidata, or {}."""
    saved = web.load_json(WIKIDATA)
    if saved.get(com_name):
        return saved[com_name]

    # The Wikidata item for the bird's article
    qid = None
    for title in filter(None, (sci_name, com_name)):
        try:
            data = web.get_json(f"https://{web.WIKI_LANG}.wikipedia.org/w/api.php?action=query"
                                "&format=json&prop=pageprops&ppprop=wikibase_item&redirects=1"
                                "&titles=" + urllib.parse.quote(title))
            qid = next(iter(data["query"]["pages"].values())).get("pageprops", {}).get("wikibase_item")
        except Exception:
            qid = None
        if qid:
            break
    if not qid:
        return {}

    # Conservation status, then up the family tree to the family and order
    out = {"source": "wikidata"}
    try:
        item = entity(qid)
        status = claim(item, "P141")                    # IUCN status
        if status:
            label = entity(status).get("labels", {}).get("en", {}).get("value", "")
            if label:
                out["conservation"] = label.title()
        for _ in range(8):
            parent = claim(item, "P171")
            if not parent:
                break
            item = entity(parent)
            rank = claim(item, "P105")
            if rank == RANK_FAMILY:
                out["family"] = claim(item, "P225")
            elif rank == RANK_ORDER:
                out["order"] = claim(item, "P225")
                break
    except Exception as e:
        print(f"Wikidata lookup failed: {e}")
    if len(out) > 1:
        saved[com_name] = out
        web.save_json(WIKIDATA, saved)
    return out


def entity(qid):
    """A Wikidata item."""
    return web.get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
                        "&props=claims|labels&languages=en&ids=" + qid)["entities"][qid]


def claim(item, prop):
    """First value of a Wikidata property: an item id, or text."""
    try:
        value = item["claims"][prop][0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    return value.get("id") if isinstance(value, dict) else value
