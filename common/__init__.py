"""Code shared by both displays."""

import os
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the bbbb-display folder
CACHE = os.path.join(ROOT, "cache")     # downloaded photos, songs, poems etc. Safe to delete.

_errors = {}


def log_error():
    """Print the error being handled, in full - but the same one at most once an hour."""
    text = traceback.format_exc()
    if time.time() - _errors.get(text, 0) >= 3600:
        _errors[text] = time.time()
        print("Error:\n" + text.rstrip())
