"""A bird's photo and its credit, from photos/ and common/birdinfo.json
(made by tools/build_birdinfo.py). To use your own photo, replace the file in
photos/ and change its photo_credit in birdinfo.json.
"""

import os

from common import ROOT, bird_info

PHOTOS = os.path.join(ROOT, "photos")


def get_photo(com_name, sci_name=None):
    """(path, credit), or (None, None) if the bird has no photo."""
    entry = bird_info(com_name, sci_name)
    path = os.path.join(PHOTOS, entry.get("photo") or "-")
    if not os.path.exists(path):
        print(f"No photo of {com_name} in photos/ - add it with tools/build_birdinfo.py")
        return None, None
    return path, entry.get("photo_credit")
