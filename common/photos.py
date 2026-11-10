"""A bird's photo and its credit, from photos_info/ (the photo, and birdinfo.json)."""

import os

from common import PHOTOS_INFO, bird_info


def get_photo(com_name, sci_name=None):
    """(path, credit), or (None, None) if the bird has no photo."""
    entry = bird_info(com_name, sci_name)
    path = os.path.join(PHOTOS_INFO, entry.get("photo") or "-")
    if not os.path.exists(path):
        print(f"No photo of {com_name} in photos_info/")
        return None, None
    return path, entry.get("photo_credit")
