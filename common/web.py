"""The IP address, web lookups (poems) and saved files."""

import json
import os
import re
import socket
import urllib.request

USER_AGENT = "bbbb-display/1.0 (Raspberry Pi bird display)"
TIMEOUT = 15            # seconds per request


# --- Downloads ---

def ip_address():
    """This Pi's address on the local network, or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def get_json(url):
    return json.loads(get(url).decode("utf-8", errors="replace"))


# --- Saved files ---

def load_json(path, default=None):
    """Contents of a JSON file, or default ({}) if it's missing or damaged."""
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
