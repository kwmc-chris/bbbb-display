"""Code shared by both displays."""

import json
import os
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the bbbb-display folder
CACHE = os.path.join(ROOT, "cache")     # prepared recordings, downloaded poems
BIRD_INFO = os.path.join(ROOT, "common", "birdinfo.json")   # names, facts and photo credits for each bird

_errors = {}


def log_error():
    """Print the current error in full; the same error at most once an hour."""
    text = traceback.format_exc()
    if time.time() - _errors.get(text, 0) >= 3600:
        _errors[text] = time.time()
        print("Error:\n" + text.rstrip())


def bird_info(com_name, sci_name=None):
    """The bird's entry in birdinfo.json, by BirdNET name or scientific name, or {}."""
    try:
        with open(BIRD_INFO, encoding="utf-8") as f:
            birds = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Couldn't read birdinfo.json: {e}")
        return {}
    entry = birds.get(com_name)
    if not entry and sci_name:
        entry = next((e for e in birds.values() if isinstance(e, dict) and sci_name in _as_list(e.get("sci"))), None)
    return entry or {}


def _as_list(value):
    """A name or list of names, as a list."""
    return [value] if isinstance(value, str) else value or []
