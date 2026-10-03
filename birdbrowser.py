#!/usr/bin/env python3
"""
birdbrowser.py - buttons and BROWSE pages for bbbb-display.py.

    Buttons()                       read buttons A/B/C/D
    recent_species(db)              species to browse, most recent first
    species_times(db, name, date)   times a species was heard
    render_page(...)                draw one browse page

Page: photo top left; names, order/family and times heard top right; five
tiles (habitat, food, nesting, behaviour, UK status) with a short description
below. Birds not in birdfacts.json get a longer description and one global
conservation tile instead.

Tile icons are drawn by code, unless you put a PNG in the icons folder
(e.g. icons/trees.png) - see section 5.

Test:
    python3 birdbrowser.py --test-buttons          print each button pressed
    python3 birdbrowser.py --icon-sheet icons.png  all icons on their tiles

Sections: 1 Settings, 2 Imports, 3 Buttons, 4 Data, 5 Icons, 6 Tiles,
          7 Page, 8 Test
"""

# =============================================================================
# 1. SETTINGS
# =============================================================================

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Buttons (BCM pin numbers on the Inky Impression 4"; C is 25 on the 13.3")
BUTTON_PINS = {"A": 5, "B": 6, "C": 16, "D": 24}
DEBOUNCE_SECONDS = 0.3            # ignore repeat presses of one button within this
EXTRA_PRESS_WAIT_SECONDS = 0.6    # wait to catch quick multiple presses

# Content
RECENT_SPECIES_LIMIT = 30         # species in the browse list
TIMES_SHOWN = 10                  # detection times listed
DESCRIPTION_LINES = 2             # description under the tiles (fewer if no room)
FALLBACK_DESCRIPTION_LINES = 5    # description for birds not in birdfacts.json

# Layout (pixels)
PAGE_MARGIN = 14
PHOTO_SIZE = (170, 140)
TILE_SIZE = 62
ICON_PADDING = 9                  # tile edge to icon

PAGE_FONTS = {                    # (font file, size)
    "name": ("DejaVuSans-Bold.ttf", 26),
    "sci": ("DejaVuSans-Oblique.ttf", 17),
    "body": ("DejaVuSans.ttf", 14),
    "bold": ("DejaVuSans-Bold.ttf", 15),
    "small": ("DejaVuSans.ttf", 13),
    "tiny": ("DejaVuSans.ttf", 10),
    "tile_label": ("DejaVuSans.ttf", 14),
    "tile_value": ("DejaVuSans-Bold.ttf", 14),
    "code": ("DejaVuSans-Bold.ttf", 22),        # "LC", "RED"
    "code_small": ("DejaVuSans-Bold.ttf", 13),  # "AMBER", "GREEN"
}
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

COLOURS = {                       # the screen's six inks
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}
TILE_COLOURS = {
    "habitat": (0, 0, 255),
    "food": (0, 255, 0),
    "nesting": (255, 255, 0),
    "behavior": (255, 128, 0),    # orange: dithered (no orange ink)
}
ICON_COLOURS = {                  # black on yellow, where white is too faint
    "habitat": COLOURS["white"], "food": COLOURS["white"],
    "nesting": COLOURS["black"], "behavior": COLOURS["white"],
}

# Your own icons: PNG named after the icon (e.g. trees.png), square (ideally
# 400x400), dark shapes on transparent or white. Missing ones are drawn.
ICON_DIR = os.path.join(SCRIPT_DIR, "icons")
ICON_MIN_OPACITY = 128            # a pixel is part of the icon if at least this opaque
ICON_MAX_BRIGHTNESS = 128         # ...and at most this bright (0-255)

# =============================================================================
# 2. IMPORTS AND HELPERS
# =============================================================================

import math
import queue
import re
import sqlite3
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(key):
    name, size = PAGE_FONTS[key]
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(draw, text, fnt, max_width):
    """Split text into lines no wider than max_width."""
    words, lines, line = text.split(), [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _wrap_limit(draw, text, fnt, max_width, max_lines):
    """Up to max_lines lines; adds "…" if text was cut off."""
    lines = _wrap(draw, text, fnt, max_width)
    if len(lines) <= max_lines or max_lines <= 0:
        return lines[:max(max_lines, 0)]
    last = lines[max_lines - 1]
    while last and draw.textlength(last + "…", font=fnt) > max_width:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    return lines[:max_lines - 1] + [last.rstrip(",;:") + "…"]


def _centred(draw, text, fnt, centre_x, y, fill):
    w = draw.textlength(text, font=fnt)
    draw.text((centre_x - w / 2, y), text, font=fnt, fill=fill)

# =============================================================================
# 3. BUTTONS  (pressed = pin pulled low; uses gpiod, or RPi.GPIO if missing)
# =============================================================================

class Buttons:
    """presses = Buttons().wait(30)  ->  e.g. ["D", "D"], or [] after 30 s"""

    def __init__(self):
        self._last_press = {}
        try:
            self._setup_gpiod()
            self.backend = "gpiod"
        except Exception as gpiod_error:
            try:
                self._setup_rpigpio()
                self.backend = "RPi.GPIO"
            except Exception as rpi_error:
                raise RuntimeError(f"gpiod: {gpiod_error}; RPi.GPIO: {rpi_error}")

    def _setup_gpiod(self):
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge

        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.FALLING)
        chip = gpiodevice.find_chip_by_platform()
        self._offsets = {chip.line_offset_from_id(pin): label
                         for label, pin in BUTTON_PINS.items()}
        self._request = chip.request_lines(
            consumer="birdnet-display-buttons",
            config=dict.fromkeys(self._offsets.keys(), settings))

    def _setup_rpigpio(self):
        import RPi.GPIO as GPIO
        self._queue = queue.Queue()
        GPIO.setmode(GPIO.BCM)
        for label, pin in BUTTON_PINS.items():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(pin, GPIO.FALLING, bouncetime=250,
                                  callback=lambda channel, l=label: self._queue.put(l))

    def _accept(self, label):
        """Debounce."""
        now = time.monotonic()
        if now - self._last_press.get(label, 0) < DEBOUNCE_SECONDS:
            return False
        self._last_press[label] = now
        return True

    def wait(self, timeout):
        """Wait up to timeout seconds; returns presses (including ones made
        while the screen was refreshing)."""
        presses = []
        if self.backend == "gpiod":
            if self._request.wait_edge_events(timeout):
                time.sleep(EXTRA_PRESS_WAIT_SECONDS)
                for event in self._request.read_edge_events():
                    label = self._offsets.get(event.line_offset)
                    if label and self._accept(label):
                        presses.append(label)
        else:
            try:
                presses.append(self._queue.get(timeout=timeout))
                time.sleep(EXTRA_PRESS_WAIT_SECONDS)
                while True:
                    presses.append(self._queue.get_nowait())
            except queue.Empty:
                pass
        return presses

    def clear(self):
        """Discard waiting presses."""
        if self.backend == "gpiod":
            while self._request.wait_edge_events(0):
                self._request.read_edge_events()
        else:
            while not self._queue.empty():
                self._queue.get_nowait()

# =============================================================================
# 4. DATA  (BirdNET-Pi's database, read-only)
# =============================================================================

def _connect(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def recent_species(db_path, limit=RECENT_SPECIES_LIMIT):
    """[{Com_Name, Sci_Name, last_heard, total}], most recent first."""
    con = _connect(db_path)
    try:
        return [dict(r) for r in con.execute(
            "SELECT Com_Name, Sci_Name, MAX(Date || ' ' || Time) AS last_heard, "
            "COUNT(*) AS total FROM detections "
            "GROUP BY Com_Name ORDER BY last_heard DESC LIMIT ?", (limit,))]
    finally:
        con.close()


def species_times(db_path, com_name, date):
    """["HH:MM", ...] for one species on one date, earliest first."""
    con = _connect(db_path)
    try:
        return [r[0][:5] for r in con.execute(
            "SELECT Time FROM detections WHERE Com_Name = ? AND Date = ? ORDER BY Time",
            (com_name, date))]
    finally:
        con.close()

# =============================================================================
# 5. ICONS
#    Each icon = drawing commands on a 100x100 grid ((0,0) top left).
#    fill=255 draws, fill=0 cuts a hole. Drawn at 400x400, shrunk, then made
#    pure on/off so edges stay crisp. The result is a stencil the tile colours in.
#    A PNG in ICON_DIR with the icon's name replaces the drawn version.
#    Check with:  python3 birdbrowser.py --icon-sheet icons.png
# =============================================================================

def _bird(d, x, y, s=1.0, fill=255):
    """Perched bird facing right; (x, y) = body centre, s = scale."""
    d.ellipse([x - 22 * s, y - 12 * s, x + 14 * s, y + 12 * s], fill=fill)     # body
    d.ellipse([x + 4 * s, y - 24 * s, x + 24 * s, y - 4 * s], fill=fill)       # head
    d.polygon([(x + 22 * s, y - 17 * s), (x + 32 * s, y - 13 * s),
               (x + 22 * s, y - 10 * s)], fill=fill)                           # beak
    d.polygon([(x - 18 * s, y - 2 * s), (x - 38 * s, y + 10 * s),
               (x - 30 * s, y + 14 * s)], fill=fill)                           # tail


def _tree(d, x, base, h=60, w=34):
    """Conifer standing on `base`."""
    d.polygon([(x, base - h), (x - w / 2, base - 12), (x + w / 2, base - 12)], fill=255)
    d.rectangle([x - 3, base - 14, x + 3, base], fill=255)


def _sine(d, y, amp=7, wavelength=30, width=7, x0=4, x1=96):
    """Wavy line at height y."""
    pts = [(x, y + amp * math.sin((x - x0) / wavelength * 2 * math.pi))
           for x in range(x0, x1 + 1, 2)]
    d.line(pts, fill=255, width=width, joint="curve")


def _waves(d, y0, n=3):
    for i in range(n):
        _sine(d, y0 + i * 20)


ICONS = {
    # Habitat
    "trees": lambda d: (_tree(d, 30, 88), _tree(d, 66, 88, 74, 40),
                        d.rectangle([6, 86, 94, 94], fill=255)),
    "town": lambda d: (d.rectangle([8, 46, 40, 92], fill=255),
                       d.polygon([(4, 48), (24, 26), (44, 48)], fill=255),
                       d.rectangle([48, 20, 92, 92], fill=255),
                       [d.rectangle([56 + c * 14, 30 + r * 16, 64 + c * 14, 38 + r * 16], fill=0)
                        for r in range(3) for c in range(3)]),                 # windows
    "water": lambda d: (_waves(d, 40, 3),),
    "grass": lambda d: (d.ellipse([60, 8, 88, 36], fill=255),                  # sun
                        [d.polygon([(x, 92), (x + 5, 58 + (x % 3) * 6), (x + 10, 92)], fill=255)
                         for x in range(4, 92, 11)]),
    # Food
    "insects": lambda d: (d.ellipse([36, 32, 64, 86], fill=255), d.ellipse([40, 14, 60, 34], fill=255),
                          [d.line([(50 + sx * 12, y), (50 + sx * 34, y + dy)], fill=255, width=5)
                           for sx in (-1, 1) for y, dy in ((44, -12), (58, 0), (72, 14))],
                          d.line([(44, 16), (34, 2)], fill=255, width=4),
                          d.line([(56, 16), (66, 2)], fill=255, width=4)),
    "seeds": lambda d: ([d.ellipse([x, y, x + 22, y + 34], fill=255)
                         for x, y in ((14, 46), (40, 22), (62, 50))],),
    "fruit": lambda d: ([d.ellipse([x, y, x + 30, y + 30], fill=255) for x, y in ((12, 52), (50, 56), (32, 30))],
                        d.line([(47, 30), (60, 6)], fill=255, width=5),
                        d.line([(27, 52), (60, 6)], fill=255, width=4),
                        d.line([(65, 56), (60, 6)], fill=255, width=4)),
    "fish": lambda d: (d.ellipse([10, 30, 72, 70], fill=255),
                       d.polygon([(66, 50), (94, 28), (94, 72)], fill=255),
                       d.ellipse([22, 42, 30, 50], fill=0)),                   # eye
    "plants": lambda d: (d.line([(50, 94), (50, 36)], fill=255, width=8),
                         d.ellipse([12, 30, 50, 52], fill=255), d.ellipse([50, 14, 90, 38], fill=255)),
    "worm": lambda d: (_sine(d, 52, amp=14, wavelength=40, width=12, x0=10, x1=82),
                       d.ellipse([74, 38, 92, 56], fill=255)),
    "animals": lambda d: (d.ellipse([14, 40, 74, 84], fill=255),                 # mouse
                          d.polygon([(66, 52), (94, 66), (68, 76)], fill=255),
                          d.ellipse([54, 30, 74, 50], fill=255),
                          d.arc([0, 50, 30, 96], 90, 270, fill=255, width=5)),
    "omnivore": lambda d: (d.ellipse([8, 40, 46, 80], fill=255), d.line([(27, 40), (34, 22)], fill=255, width=5),
                           d.ellipse([58, 42, 82, 86], fill=255), d.ellipse([62, 26, 78, 42], fill=255),
                           [d.line([(70 + sx * 8, y), (70 + sx * 22, y + dy)], fill=255, width=4)
                            for sx in (-1, 1) for y, dy in ((52, -8), (66, 6))]),
    # Nesting
    "cup": lambda d: (d.chord([6, 28, 94, 96], 0, 180, fill=255),
                      [d.ellipse([x - 4, 34, x + 22, 70], fill=0) for x in (24, 42, 60)],
                      [d.ellipse([x, 38, x + 18, 66], fill=255) for x in (24, 42, 60)]),   # eggs
    "dome": lambda d: (d.ellipse([14, 12, 86, 92], fill=255), d.ellipse([38, 40, 62, 64], fill=0)),
    "cavity": lambda d: (d.rectangle([28, 4, 72, 96], fill=255), d.ellipse([40, 32, 60, 52], fill=0),
                         d.line([(50, 60), (62, 62)], fill=0, width=3)),
    "tree": lambda d: (d.ellipse([10, 6, 90, 62], fill=255),
                       d.polygon([(42, 56), (58, 56), (66, 96), (34, 96)], fill=255)),
    "ground": lambda d: (d.rectangle([4, 80, 96, 90], fill=255),
                         d.chord([22, 46, 78, 96], 180, 360, fill=255),
                         [d.ellipse([x, 54, x + 14, 70], fill=0) for x in (34, 50)]),
    "building": lambda d: (d.rectangle([18, 44, 82, 94], fill=255),
                           d.polygon([(8, 46), (50, 8), (92, 46)], fill=255),
                           d.rectangle([42, 66, 58, 94], fill=0)),                # door
    "other": lambda d: (d.ellipse([20, 20, 80, 80], fill=255), d.ellipse([34, 34, 66, 66], fill=0)),
    # Behaviour
    "ground_bird": lambda d: (_bird(d, 48, 52),
                              [d.line([(x, 96), (x + 4, 76)], fill=255, width=4) for x in range(4, 96, 9)]),
    "foliage": lambda d: (_bird(d, 52, 48, 0.9), d.line([(4, 72), (96, 64)], fill=255, width=6),
                          d.ellipse([4, 74, 26, 88], fill=255), d.ellipse([70, 70, 94, 84], fill=255)),
    "bark": lambda d: (d.rectangle([60, 0, 82, 100], fill=255),
                       d.ellipse([28, 28, 54, 72], fill=255), d.ellipse([32, 10, 52, 32], fill=255),
                       d.polygon([(52, 18), (62, 20), (52, 26)], fill=255),
                       d.polygon([(40, 70), (50, 92), (56, 70)], fill=255)),
    "flying": lambda d: (d.polygon([(4, 34), (50, 58), (96, 34), (50, 70)], fill=255),
                         d.ellipse([40, 52, 60, 74], fill=255)),
    "duck": lambda d: (_bird(d, 52, 44, 1.0), _waves(d, 70, 2)),
}

# Words that choose each icon: checked top to bottom, first match wins.
# Patterns are fragments separated by | ; \b = word boundary.
KEYWORDS = {
    "habitat": [
        ("water", r"lake|pond|river|marsh|wetland|coast|shore|\bsea|ocean|water"),
        ("trees", r"wood|forest|conifer|parkland"),
        ("town", r"town|garden|urban|village|\bpark|city"),
        ("grass", r"grass|farm|field|scrub|heath|hedge|open|moor|country"),
    ],
    "food": [
        ("insects", r"insect|\bants?\b|caterpillar|invertebrate"),
        ("worm", r"worm|snail"),
        ("seeds", r"seed|grain|nut|acorn|bud"),
        ("fruit", r"fruit|berr"),
        ("fish", r"fish"),
        ("animals", r"animal|mammal|bird|carrion|mice|vole"),
        ("omnivore", r"omnivore"),
        ("plants", r"plant|leaf|leaves|veget"),
    ],
    "nesting": [
        ("cavity", r"cavity|hole|crevice|burrow"),
        ("dome", r"dome"),
        ("cup", r"cup"),
        ("building", r"building|ledge|roof|cliff"),
        ("ground", r"ground"),
        ("tree", r"tree|branch|platform"),
    ],
    "behavior": [
        ("bark", r"bark|trunk|climb"),
        ("flying", r"aerial|fly|soar|hover|ambush|dive"),
        ("duck", r"dabbl|swim|surface|dip"),
        ("foliage", r"foliage|glean|canopy"),
        ("ground_bird", r"ground|forag|pounce|scaveng"),
    ],
}
DEFAULT_ICON = {"habitat": "trees", "food": "plants", "nesting": "other",
                "behavior": "ground_bird"}


def choose_icon(category, value):
    """("habitat", "Open Woodlands") -> "trees"."""
    for name, pattern in KEYWORDS.get(category, []):
        if re.search(pattern, value or "", re.I):
            return name
    return DEFAULT_ICON.get(category, "other")


class _Scaled:
    """Scales 100x100 grid numbers (and line widths) up to the drawing size."""

    def __init__(self, draw, factor):
        self._draw, self._k = draw, factor

    def _scale(self, a):
        if isinstance(a, (int, float)):
            return a * self._k
        if isinstance(a, (list, tuple)):
            return type(a)(self._scale(x) for x in a)
        return a

    def __getattr__(self, method):
        real = getattr(self._draw, method)

        def call(*args, **kw):
            args = [self._scale(a) for a in args]
            if "width" in kw:
                kw["width"] = int(kw["width"] * self._k)
            return real(*args, **kw)
        return call


def _to_stencil(mask, size):
    """Greyscale mask -> size x size RGBA stencil, every pixel on or off."""
    mask = mask.resize((size, size), Image.LANCZOS).point(lambda a: 255 if a >= 110 else 0)
    glyph = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    glyph.putalpha(mask)
    return glyph


_reported = set()                 # icon files already mentioned in the log


def custom_icon_path(name):
    path = os.path.join(ICON_DIR, name + ".png")
    return path if os.path.isfile(path) else None


def load_custom_icon(name, size):
    """Stencil from your PNG, or None (no file / unreadable)."""
    path = custom_icon_path(name)
    if not path:
        return None
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:
        if path not in _reported:
            print(f"Couldn't read {path} ({e}) - using the drawn icon instead.")
            _reported.add(path)
        return None
    if path not in _reported:
        print(f"Using your icon {path}")
        _reported.add(path)

    if img.width != img.height:           # centre on a square
        side = max(img.size)
        square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = square

    # Ink = opaque enough AND dark enough (treats transparent and white alike)
    opacity = img.getchannel("A").point(lambda a: 255 if a >= ICON_MIN_OPACITY else 0)
    darkness = img.convert("L").point(lambda v: 255 if v <= ICON_MAX_BRIGHTNESS else 0)
    ink = Image.composite(darkness, Image.new("L", img.size, 0), opacity)
    return _to_stencil(ink, size)


def draw_icon(name, size, draw_size=400):
    """Stencil of a drawn icon."""
    big = Image.new("L", (draw_size, draw_size), 0)
    ICONS[name](_Scaled(ImageDraw.Draw(big), draw_size / 100))
    return _to_stencil(big, size)


def make_icon(category, value, size):
    """Icon stencil for a tile: your PNG if present, otherwise drawn."""
    name = choose_icon(category, value)
    return load_custom_icon(name, size) or draw_icon(name, size)

# =============================================================================
# 6. TILES
# =============================================================================

IUCN_CODES = [("critically", "CR"), ("endangered", "EN"), ("vulnerable", "VU"),
              ("near threatened", "NT"), ("least", "LC"), ("data deficient", "DD")]


def uk_status_tile(status):
    """BTO list -> (code, tile colour, text colour, words)."""
    if not status:
        return "N/A", COLOURS["white"], COLOURS["black"], "Not assessed"
    s = status.lower()
    if s.startswith("red"):
        return "RED", COLOURS["red"], COLOURS["white"], "Red List"
    if s.startswith("amber"):
        return "AMBER", COLOURS["yellow"], COLOURS["black"], "Amber List"
    return "GREEN", COLOURS["green"], COLOURS["black"], "Green List"


def iucn_tile(status):
    """Global status -> (code, tile colour, text colour)."""
    code = next((c for k, c in IUCN_CODES if k in status.lower()), status[:2].upper())
    if code == "LC":
        return code, COLOURS["green"], COLOURS["black"]
    if code in ("NT", "DD"):
        return code, COLOURS["yellow"], COLOURS["black"]
    return code, COLOURS["red"], COLOURS["white"]


def draw_tile(canvas, d, centre_x, top, bg, label, value_lines,
              glyph=None, glyph_colour=None, code=None, code_colour=None, code_font=None):
    """Tile with an icon (glyph) or code, plus label and value below.
    Returns the y just below the last line drawn."""
    t = TILE_SIZE
    box = (int(centre_x - t / 2), top, int(centre_x + t / 2), top + t)
    outline = COLOURS["black"] if bg == COLOURS["white"] else None    # keep white tiles visible
    d.rounded_rectangle(box, radius=8, fill=bg, outline=outline)

    if glyph is not None:
        inner = t - 2 * ICON_PADDING
        g = glyph.resize((inner, inner))
        canvas.paste(Image.new("RGB", g.size, glyph_colour),
                     (box[0] + ICON_PADDING, box[1] + ICON_PADDING), g)
    if code:
        cw = d.textlength(code, font=code_font)
        d.text((centre_x - cw / 2, top + t / 2 - code_font.size * 0.6), code,
               font=code_font, fill=code_colour)

    y = top + t + 5
    _centred(d, label, _font("tile_label"), centre_x, y, COLOURS["black"])
    y += 18
    for line in value_lines[:2]:
        _centred(d, line, _font("tile_value"), centre_x, y, COLOURS["black"])
        y += 17
    return y

# =============================================================================
# 7. PAGE  (y = current text height)
# =============================================================================

def render_page(size, sp, times_today, details, image_path, credit, index, count,
                description=None, rotate=0):
    """One browse page. sp = a recent_species() row; details = get_details();
    image_path None = no photo."""
    width, height = size
    m = PAGE_MARGIN
    canvas = Image.new("RGB", size, COLOURS["white"])
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"
    footer_y = height - m - 12

    # --- Photo and credit (top left) ---
    pw, ph = PHOTO_SIZE
    x_text = m
    if image_path:
        try:
            img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
            canvas.paste(ImageOps.fit(img, (pw, ph), method=Image.LANCZOS), (m, m))
            if credit:
                for i, line in enumerate(_wrap(d, credit, _font("tiny"), pw)[:2]):
                    d.text((m, m + ph + 3 + i * 12), line, font=_font("tiny"),
                           fill=COLOURS["black"])
            x_text = m + pw + 18
        except Exception:
            pass

    # --- Names, order, family (top right) ---
    max_w = width - x_text - m
    y = m
    for line in _wrap(d, sp["Com_Name"], _font("name"), max_w)[:2]:
        d.text((x_text, y), line, font=_font("name"), fill=COLOURS["black"])
        y += 31
    d.text((x_text, y), sp["Sci_Name"], font=_font("sci"), fill=COLOURS["black"])
    y += 25

    for key in ("order", "family"):
        if details.get(key):
            text = details[key]
            if key == "family" and details.get("family_name"):      # add common name if it fits
                full = f"{text} ({details['family_name']})"
                if d.textlength(key.upper() + ": " + full, font=_font("body")) <= max_w:
                    text = full
            label_w = d.textlength(key.upper() + ": ", font=_font("body"))
            d.text((x_text, y), key.upper() + ":", font=_font("body"), fill=COLOURS["blue"])
            d.text((x_text + label_w, y), text, font=_font("body"), fill=COLOURS["black"])
            y += 19
    y += 6

    # --- When heard ---
    if times_today:
        n = len(times_today)
        d.text((x_text, y), f"Heard {n} time{'s' if n != 1 else ''} today",
               font=_font("bold"), fill=COLOURS["red"])
        y += 20
        d.text((x_text, y), f"First {times_today[0]}  •  Last {times_today[-1]}  •  "
               f"{sp['total']} in total", font=_font("small"), fill=COLOURS["black"])
        y += 18
        if y < 180:                           # room above the tiles
            recent = times_today[-TIMES_SHOWN:]
            label = "Recent: " if n > TIMES_SHOWN else "Times: "
            d.text((x_text, y), _wrap(d, label + "  ".join(recent), _font("small"), max_w)[0],
                   font=_font("small"), fill=COLOURS["black"])
            y += 18
    else:
        last = datetime.strptime(sp["last_heard"][:16], "%Y-%m-%d %H:%M")
        d.text((x_text, y), "Last heard " + last.strftime("%d %b, %H:%M"),
               font=_font("bold"), fill=COLOURS["red"])
        y += 20
        d.text((x_text, y), f"{sp['total']} detections in total", font=_font("small"),
               fill=COLOURS["black"])
        y += 18

    # --- Tiles: 5 equal columns, below the photo and text ---
    tile_top = max(m + ph + 30, min(y + 10, 232))
    col_w = (width - 2 * m) / 5

    def column_centre(i):
        return m + col_w * i + col_w / 2

    line_h = 18                               # description line height
    if details.get("source") == "file":
        bottom = tile_top
        for i, (key, label) in enumerate([("habitat", "Habitat"), ("food", "Food"),
                                          ("nesting", "Nesting"), ("behavior", "Behavior")]):
            value = details.get(key)
            if not value:
                continue
            bottom = max(bottom, draw_tile(
                canvas, d, column_centre(i), tile_top, TILE_COLOURS[key], label,
                _wrap(d, value, _font("tile_value"), col_w - 4),
                glyph=make_icon(key, value, 64), glyph_colour=ICON_COLOURS[key]))
        code, bg, fg, words = uk_status_tile(details.get("uk_status"))
        bottom = max(bottom, draw_tile(
            canvas, d, column_centre(4), tile_top, bg, "UK Status", [words],
            code=code, code_colour=fg,
            code_font=_font("code_small") if len(code) > 3 else _font("code")))

        # Description under the tiles: DESCRIPTION_LINES, fewer if no room
        if description:
            ty = bottom + 6
            room = (footer_y - 2 - ty) // line_h
            for line in _wrap_limit(d, description, _font("body"), width - 2 * m,
                                    min(DESCRIPTION_LINES, room)):
                d.text((m, ty), line, font=_font("body"), fill=COLOURS["black"])
                ty += line_h
    else:
        # Not in birdfacts.json: global status tile right, description left
        if details.get("conservation"):
            code, bg, fg = iucn_tile(details["conservation"])
            draw_tile(canvas, d, column_centre(4), tile_top, bg, "Conservation",
                      _wrap(d, details["conservation"], _font("tile_value"), col_w - 4),
                      code=code, code_colour=fg, code_font=_font("code"))
        ty = tile_top
        if description:
            for line in _wrap_limit(d, description, _font("body"), col_w * 4 - 10,
                                    FALLBACK_DESCRIPTION_LINES):
                d.text((m, ty), line, font=_font("body"), fill=COLOURS["black"])
                ty += 19
        d.text((m, ty + 6), "Add this bird to birdfacts.json for more details.",
               font=_font("small"), fill=COLOURS["blue"])

    # --- Navigation (bottom right) ---
    nav = f"◀ A    {index + 1} of {count}    D ▶"
    w = d.textlength(nav, font=_font("small"))
    d.text((width - m - w, footer_y), nav, font=_font("small"), fill=COLOURS["black"])

    if rotate:
        canvas = canvas.rotate(rotate)
    return canvas

# =============================================================================
# 8. TEST
# =============================================================================

def icon_sheet(path):
    """Save all icons on their tiles, marked "file" (yours) or "drawn"."""
    category_of = {}
    for cat, entries in KEYWORDS.items():
        for name, _ in entries:
            category_of.setdefault(name, cat)
    for cat, name in DEFAULT_ICON.items():
        category_of.setdefault(name, cat)

    names = [n for n in ICONS if n in category_of]
    per_row, cell_w, cell_h = 6, 110, 110
    rows = (len(names) + per_row - 1) // per_row
    sheet = Image.new("RGB", (per_row * cell_w, rows * cell_h), COLOURS["white"])
    d = ImageDraw.Draw(sheet)
    d.fontmode = "1"
    used_files = 0
    for i, name in enumerate(names):
        cat = category_of[name]
        cx = (i % per_row) * cell_w + cell_w // 2
        top = (i // per_row) * cell_h + 8
        own = load_custom_icon(name, 64)
        used_files += 1 if own else 0
        draw_tile(sheet, d, cx, top, TILE_COLOURS[cat], name, [],
                  glyph=own or draw_icon(name, 64), glyph_colour=ICON_COLOURS[cat])
        _centred(d, "file" if own else "drawn", _font("small"), cx, top + TILE_SIZE + 22,
                 COLOURS["red"] if own else COLOURS["blue"])
    sheet.save(path)
    print(f"Saved {path} - {len(names)} icons, {used_files} from {ICON_DIR}")


if __name__ == "__main__":
    import sys
    if "--icon-sheet" in sys.argv:
        i = sys.argv.index("--icon-sheet")
        icon_sheet(sys.argv[i + 1] if i + 1 < len(sys.argv) else "icons.png")
    elif "--test-buttons" in sys.argv:
        buttons = Buttons()
        print(f"Using {buttons.backend}. Press A, B, C or D (Ctrl+C to stop)...")
        while True:
            for p in buttons.wait(1):
                print("Pressed", p)
    else:
        print(__doc__)
