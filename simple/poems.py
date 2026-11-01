"""Finds a verse about a bird in PoetryDB (classic public-domain poems).

    find_verse(bird, words) -> {"lines", "title", "author"} or None

Search results are saved in cache/poems/. A different verse is picked each time.
Test:  .venv/bin/python -m simple.poems robin redbreast
"""

import os
import random
import re
import sys
import urllib.parse

from common import CACHE, web

FOLDER = os.path.join(CACHE, "poems")
MAX_LINES = 4               # longest verse shown
AVOID_REPEATS = 5           # don't reuse a bird's last 5 verses
FALLBACK_WORDS = ["bird", "birds"]
EXCLUDE = ["robin hood", "robin goodfellow", "round robin"]   # word means something else


def search(word):
    """Poems with `word` in a line. Saved once fetched; [] if offline."""
    path = os.path.join(FOLDER, web.slug(word) + ".json")
    poems = web.load_json(path, default=False)
    if poems is False:
        url = f"https://poetrydb.org/lines/{urllib.parse.quote(word)}/title,author,lines.json"
        try:
            poems = web.get_json(url)
        except Exception as e:
            print(f"PoetryDB search for '{word}' failed: {e}")
            return []
        poems = poems if isinstance(poems, list) else []   # no match = {"status": 404}
        web.save_json(path, poems)
    return poems


def verses(word):
    """The stanza around the first mention of `word` in each poem."""
    pattern = re.compile(rf"(?<![\w-]){re.escape(word)}(e?s)?(?![\w-])", re.I)
    found = []
    for poem in search(word):
        lines = poem.get("lines", [])
        for i, line in enumerate(lines):
            if pattern.search(line) and not any(x in line.lower() for x in EXCLUDE):
                start, end = i, i                  # stanza = lines between blank lines
                while start > 0 and lines[start - 1].strip():
                    start -= 1
                while end + 1 < len(lines) and lines[end + 1].strip():
                    end += 1
                if end - start >= MAX_LINES:       # long stanza: lines near the mention
                    start = max(start, min(i - 1, end - MAX_LINES + 1))
                    end = start + MAX_LINES - 1
                found.append({"lines": lines[start:end + 1],
                              "title": poem.get("title", ""), "author": poem.get("author", "")})
                break
    return found


def find_verse(bird, words):
    pool = []
    for word in words:                             # earlier words preferred
        pool += verses(word)
        if len(pool) >= 3:
            break
    for word in FALLBACK_WORDS:
        if pool:
            break
        pool += verses(word)
    if not pool:
        return None

    history_file = os.path.join(FOLDER, "recent.json")
    history = web.load_json(history_file)
    recent = history.get(bird, [])
    key = lambda v: f"{v['author']}|{v['title']}|{v['lines'][0]}"
    verse = random.choice([v for v in pool if key(v) not in recent] or pool)
    history[bird] = (recent + [key(verse)])[-AVOID_REPEATS:]
    web.save_json(history_file, history)
    return verse


if __name__ == "__main__":
    v = find_verse("test", sys.argv[1:] or ["robin"])
    print("\n".join(v["lines"]) + f"\n  — {v['author']}, {v['title']}" if v else "Nothing found.")
