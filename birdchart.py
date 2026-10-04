#!/usr/bin/env python3
"""
birdchart.py - today's species-by-hour chart for bbbb-display.py (button C).

    make_chart(size, db, style)   "drawn": drawn for the e-ink (default)
                                  "birdnet": BirdNET-Pi's own chart image, shrunk

Species down the side (busiest first), hours across the top (current hour in
red), coloured squares with the count per hour.

Test:  python3 birdchart.py --preview chart.png [--date YYYY-MM-DD] [--style birdnet]

Sections: 1 Settings, 2 Imports, 3 Data, 4 Drawn chart, 5 BirdNET-Pi image,
          6 make_chart, 7 Test
"""

# =============================================================================
# 1. SETTINGS
# =============================================================================

import os

BIRDNET_CHART_DIR = os.path.expanduser("~/BirdSongs/Extracted/Charts")   # BirdNET-Pi's chart images

COLOURS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}

# (lowest, highest or None = and above, square colour, number colour) - also the legend
COUNT_COLOURS = [
    (1, 2, COLOURS["yellow"], COLOURS["black"]),
    (3, 9, COLOURS["green"], COLOURS["black"]),
    (10, 24, COLOURS["blue"], COLOURS["white"]),
    (25, None, COLOURS["red"], COLOURS["white"]),
]

CHART_MARGIN = 10
NAME_COLUMN_WIDTH = 150
TOTAL_COLUMN_WIDTH = 30          # "All" column
ROW_HEIGHT = 21
MIN_HOURS_SHOWN = 12

CHART_FONTS = {
    "title": ("DejaVuSans-Bold.ttf", 18),
    "name": ("DejaVuSans.ttf", 12),
    "total": ("DejaVuSans-Bold.ttf", 12),
    "cell": ("DejaVuSans-Bold.ttf", 11),
    "small": ("DejaVuSans.ttf", 11),
}
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

# =============================================================================
# 2. IMPORTS AND HELPERS
# =============================================================================

import glob
import sqlite3
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(key):
    name, size = CHART_FONTS[key]
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit_text(d, text, fnt, max_width):
    """Shorten with "…" to fit max_width."""
    if d.textlength(text, font=fnt) <= max_width:
        return text
    while text and d.textlength(text + "…", font=fnt) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _count_colours(n):
    for low, high, fill, text in COUNT_COLOURS:
        if n >= low and (high is None or n <= high):
            return fill, text
    return COLOURS["white"], COLOURS["black"]


def _today():
    return datetime.now().strftime("%Y-%m-%d")

# =============================================================================
# 3. DATA
# =============================================================================

def daily_counts(db_path, date):
    """{species: {hour: count}} for one date."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute(
            "SELECT Com_Name, CAST(substr(Time, 1, 2) AS INTEGER), COUNT(*) "
            "FROM detections WHERE Date = ? GROUP BY Com_Name, 2", (date,)).fetchall()
    finally:
        con.close()
    counts = {}
    for name, hour, n in rows:
        counts.setdefault(name, {})[hour] = n
    return counts

# =============================================================================
# 4. DRAWN CHART
# =============================================================================

def _hours_to_show(counts, now_hour):
    """First active hour to last (or now), widened to MIN_HOURS_SHOWN."""
    active = sorted({h for hours in counts.values() for h in hours})
    start, end = active[0], max(active[-1], min(now_hour, 23))
    while end - start + 1 < MIN_HOURS_SHOWN:
        if start > 0:
            start -= 1
        if end - start + 1 < MIN_HOURS_SHOWN and end < 23:
            end += 1
        if start == 0 and end == 23:
            break
    return list(range(start, end + 1))


def render_chart(size, date, counts, rotate=0):
    width, height = size
    m = CHART_MARGIN
    canvas = Image.new("RGB", size, COLOURS["white"])
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"

    is_today = date == _today()
    now_hour = datetime.now().hour if is_today else 23

    # Title and summary
    day = datetime.strptime(date, "%Y-%m-%d")
    total = sum(sum(h.values()) for h in counts.values())
    d.text((m, m), f"Today's birds  •  {day.strftime('%a %d %b')}", font=_font("title"),
           fill=COLOURS["black"])
    summary = f"{total} detections, {len(counts)} species"
    w = d.textlength(summary, font=_font("name"))
    d.text((width - m - w, m + 5), summary, font=_font("name"), fill=COLOURS["blue"])

    if not counts:
        d.text((m, m + 60), "No detections yet today.", font=_font("title"), fill=COLOURS["black"])
        return canvas.rotate(rotate) if rotate else canvas

    # Grid layout
    hours = _hours_to_show(counts, now_hour)
    labels_top = m + 34
    grid_top = labels_top + 16
    legend_h = 22
    grid_left = m + NAME_COLUMN_WIDTH + TOTAL_COLUMN_WIDTH
    cell_w = (width - m - grid_left) / len(hours)
    max_rows = int((height - grid_top - legend_h - m) // ROW_HEIGHT)

    # Busiest first; if too many, last row becomes "+ N more species"
    species = sorted(counts, key=lambda s: -sum(counts[s].values()))
    shown, hidden = species[:max_rows], species[max_rows:]
    if hidden:
        shown, hidden = species[:max_rows - 1], species[max_rows - 1:]

    # Hour labels
    for i, h in enumerate(hours):
        centre = grid_left + cell_w * (i + 0.5)
        label = str(h)
        lw = d.textlength(label, font=_font("small"))
        colour = COLOURS["red"] if (is_today and h == now_hour) else COLOURS["black"]
        d.text((centre - lw / 2, labels_top), label, font=_font("small"), fill=colour)
    d.text((m + NAME_COLUMN_WIDTH + 2, labels_top), "All", font=_font("small"), fill=COLOURS["black"])

    # Species rows
    for r, name in enumerate(shown):
        y = grid_top + r * ROW_HEIGHT
        if r % 2 == 0:
            d.line((m, y + ROW_HEIGHT - 1, width - m, y + ROW_HEIGHT - 1),
                   fill=COLOURS["black"], width=1)
        d.text((m, y + 4), _fit_text(d, name, _font("name"), NAME_COLUMN_WIDTH - 6),
               font=_font("name"), fill=COLOURS["black"])
        d.text((m + NAME_COLUMN_WIDTH + 2, y + 4), str(sum(counts[name].values())),
               font=_font("total"), fill=COLOURS["black"])
        for i, h in enumerate(hours):
            n = counts[name].get(h, 0)
            if not n:
                continue
            x0 = grid_left + cell_w * i + 1
            box = (int(x0), y + 2, int(x0 + cell_w - 2), y + ROW_HEIGHT - 3)
            fill, text_colour = _count_colours(n)
            d.rectangle(box, fill=fill)
            label = str(n) if n < 100 else "99+"
            lw = d.textlength(label, font=_font("cell"))
            if lw <= cell_w - 2:
                d.text(((box[0] + box[2]) / 2 - lw / 2, y + 4), label, font=_font("cell"),
                       fill=text_colour)

    if hidden:
        y = grid_top + len(shown) * ROW_HEIGHT
        n = sum(sum(counts[s].values()) for s in hidden)
        d.text((m, y + 4), f"+ {len(hidden)} more species ({n} detections)",
               font=_font("name"), fill=COLOURS["blue"])

    # Legend and button hints
    ly = height - m - 14
    x = m
    d.text((x, ly), "Detections per hour:", font=_font("small"), fill=COLOURS["black"])
    x += d.textlength("Detections per hour:", font=_font("small")) + 8
    for low, high, fill, _ in COUNT_COLOURS:
        d.rectangle((x, ly + 1, x + 14, ly + 13), fill=fill)
        x += 18
        label = f"{low}+" if high is None else f"{low}–{high}"
        d.text((x, ly), label, font=_font("small"), fill=COLOURS["black"])
        x += d.textlength(label, font=_font("small")) + 12
    # (button hints are drawn bottom right by bbbb-display.py)

    if rotate:
        canvas = canvas.rotate(rotate)
    return canvas

# =============================================================================
# 5. BIRDNET-PI'S OWN CHART IMAGE
# =============================================================================

def find_birdnet_chart(date):
    for pattern in (f"Combo-{date}.png", f"*{date}*.png"):
        matches = sorted(glob.glob(os.path.join(BIRDNET_CHART_DIR, pattern)))
        if matches:
            return matches[0]
    return None


def render_birdnet_image(size, path, rotate=0):
    """Shrink to fit, nothing cropped."""
    canvas = Image.new("RGB", size, COLOURS["white"])
    img = ImageOps.contain(Image.open(path).convert("RGB"), size, method=Image.LANCZOS)
    canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return canvas.rotate(rotate) if rotate else canvas

# =============================================================================
# 6. make_chart
# =============================================================================

def make_chart(size, db_path, style="drawn", rotate=0, date=None):
    """Chart image. "birdnet" falls back to drawn if there's no image for today."""
    date = date or _today()
    if style == "birdnet":
        path = find_birdnet_chart(date)
        if path:
            return render_birdnet_image(size, path, rotate)
        print(f"No BirdNET-Pi chart image found in {BIRDNET_CHART_DIR} - drawing one instead.")
    return render_chart(size, date, daily_counts(db_path, date), rotate=rotate)

# =============================================================================
# 7. TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Save a picture of the daily chart")
    p.add_argument("--db", default=os.path.expanduser("~/BirdNET-Pi/scripts/birds.db"))
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--style", choices=["drawn", "birdnet"], default="drawn")
    p.add_argument("--preview", default="chart.png")
    a = p.parse_args()
    make_chart((600, 400), a.db, a.style, date=a.date).save(a.preview)
    print(f"Saved {a.preview}")
