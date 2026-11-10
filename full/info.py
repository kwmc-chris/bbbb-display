"""Facts about a bird for the full display, from photos_info/birdinfo.json.

    description(name, sci)   opening text of its Wikipedia article, cut to length
    wiki_link(name, sci)     link to the article (for the QR code)
    details(name, sci)       everything else: order, family, tile facts, weight
"""

import re

from common import bird_info


def description(com_name, sci_name=None, sentences=1, max_chars=170):
    """Opening text of the article, cut to length, or None."""
    text = bird_info(com_name, sci_name).get("description")
    return first_sentences(text, sentences, max_chars) if text else None


def wiki_link(com_name, sci_name=None):
    """Link to the article, or None."""
    return bird_info(com_name, sci_name).get("wiki_url")


def details(com_name, sci_name=None):
    """The bird's entry in birdinfo.json, e.g. {"order", "habitat", "diet", ..., "mass_g"}, or {}."""
    return bird_info(com_name, sci_name)


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
