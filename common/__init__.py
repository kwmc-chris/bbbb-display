"""Code shared by both displays."""

import os
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the bbbb-display folder
CACHE = os.path.join(ROOT, "cache")     # downloaded photos, recordings, poems

_errors = {}


def log_error():
    """Print the current error in full; the same error at most once an hour."""
    text = traceback.format_exc()
    if time.time() - _errors.get(text, 0) >= 3600:
        _errors[text] = time.time()
        print("Error:\n" + text.rstrip())
