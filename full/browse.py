"""Browse pages for the full display: one page per bird, most recent first.

Photo, names and times heard at the top; five tiles (habitat, diet, lifestyle,
migration, UK status); its weight compared with a robin or a swan; description
and QR code to Wikipedia below. The facts are in photos_info/birdinfo.json.
"""

from datetime import datetime

from PIL import Image, ImageDraw, ImageOps

from common import birdnet, screen

# settings
RECENT_SPECIES_LIMIT = 30         # birds in the browse list
TIMES_SHOWN = 10                  # detection times listed
DESCRIPTION_LINES = 4             # description lines under the tiles
QR_SIZES = (3, 2)                 # pixels per QR square, largest that fits
QR_GAP = 12                       # space between description and QR code

PAGE_MARGIN = 14
PHOTO_SIZE = (170, 140)
TILE_HEIGHT = 44                  # the coloured box of each tile
ROBIN_G, SWAN_G = 18, 10000       # weights the bird is compared with

FONTS = {
    "name": ("DejaVuSans-Bold.ttf", 26),
    "sci": ("DejaVuSans-Oblique.ttf", 17),
    "body": ("DejaVuSans.ttf", 14),
    "bold": ("DejaVuSans-Bold.ttf", 15),
    "small": ("DejaVuSans.ttf", 13),
    "tiny": ("DejaVuSans.ttf", 10),
    "tile_label": ("DejaVuSans.ttf", 14),
    "tile_value": ("DejaVuSans-Bold.ttf", 15),
}

COLOURS = {                       # the screen's six inks
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}
ORANGE = (255, 128, 0)            # mixed from the inks
TILES = [                         # (birdinfo.json field, label, box colour, text colour)
    ("habitat", "Habitat", COLOURS["blue"], COLOURS["white"]),
    ("diet", "Diet", COLOURS["green"], COLOURS["black"]),
    ("lifestyle", "Lifestyle", COLOURS["yellow"], COLOURS["black"]),
    ("migration", "Migration", ORANGE, COLOURS["white"]),
]
UK_STATUS_COLOURS = {             # UK status tile: list -> (box colour, text colour)
    "Red": (COLOURS["red"], COLOURS["white"]),
    "Amber": (COLOURS["yellow"], COLOURS["black"]),
    "Green": (COLOURS["green"], COLOURS["black"]),
}


# --- Helpers ---

def _font(key):
    return screen.font(*FONTS[key])


def _wrap_limit(draw, text, fnt, max_width, max_lines):
    """Up to max_lines lines; ends with "…" if the text was cut."""
    lines = screen.wrap(draw, text, fnt, max_width)
    if len(lines) <= max_lines or max_lines <= 0:
        return lines[:max(max_lines, 0)]
    last = lines[max_lines - 1]
    while last and draw.textlength(last + "…", font=fnt) > max_width:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    return lines[:max_lines - 1] + [last.rstrip(",;:") + "…"]


def _centred(draw, text, fnt, centre_x, y, fill):
    w = draw.textlength(text, font=fnt)
    draw.text((centre_x - w / 2, y), text, font=fnt, fill=fill)


# --- Data ---

def recent_species():
    """[{Com_Name, Sci_Name, last_heard, total}], most recently heard first."""
    return [dict(r) for r in birdnet.query(
        "SELECT Com_Name, Sci_Name, MAX(Date || ' ' || Time) AS last_heard, COUNT(*) AS total "
        "FROM detections GROUP BY Com_Name ORDER BY last_heard DESC LIMIT ?",
        RECENT_SPECIES_LIMIT)]


def times_heard(com_name, date):
    """["HH:MM", ...] for one bird on one date, earliest first."""
    return [r[0][:5] for r in birdnet.query(
        "SELECT Time FROM detections WHERE Com_Name = ? AND Date = ? ORDER BY Time", com_name, date)]


# --- QR code ---

def qr_images(text):
    """The QR code as pictures, one per size in QR_SIZES ([] if qrcode isn't installed)."""
    try:
        import qrcode
    except ImportError:
        return []
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    small = Image.new("1", (n, n), 1)
    small.putdata([0 if dark else 1 for row in matrix for dark in row])
    return [small.resize((n * s, n * s), Image.NEAREST).convert("RGB") for s in QR_SIZES]


def place_qr(canvas, images, right, top, max_bottom):
    """Paste the largest QR picture that fits, top-right corner at (right, top).
    Returns its width (0 if none fits)."""
    for img in images or []:
        if top + img.height <= max_bottom:
            canvas.paste(img, (right - img.width, top))
            return img.width
    return 0


# --- Tiles and weight ---

def draw_tile(d, x0, x1, top, label, value, bg, fg):
    """A tile between x0 and x1: label, then the value in a coloured box.
    Returns the y just below the box."""
    _centred(d, label, _font("tile_label"), (x0 + x1) / 2, top, COLOURS["black"])
    top += 19
    d.rounded_rectangle((x0, top, x1, top + TILE_HEIGHT), radius=8, fill=bg,
                        outline=COLOURS["black"] if bg == COLOURS["white"] else None)
    lines = screen.wrap(d, value, _font("tile_value"), x1 - x0 - 8)[:2]
    y = top + TILE_HEIGHT / 2 - len(lines) * 9
    for line in lines:
        _centred(d, line, _font("tile_value"), (x0 + x1) / 2, y, fg)
        y += 18
    return top + TILE_HEIGHT


def weight_text(grams):
    """e.g. "Weighs 490 g - as much as 27 robins", or None.
    Under 1 kg it's compared with a robin, over with a swan."""
    if not grams:
        return None
    if grams < 1000:
        weight, n, thing = f"{grams:.0f} g", grams / ROBIN_G, "robin"
    else:
        weight, n, thing = f"{grams / 1000:.1f} kg", grams / SWAN_G, "swan"
    if n >= 1.5:
        like = f"as much as {round(n)} {thing}s"
    elif n >= 0.7:
        like = f"about the same as a {thing}"
    else:
        parts = {2: "half", 3: "a third of", 4: "a quarter of", 5: "a fifth of"}
        like = f"about {parts.get(round(1 / n), f'1/{round(1 / n)} of')} a {thing}"
    return f"Weighs {weight} - {like}"


# --- Page (y = how far down the text has got) ---

def render_page(size, sp, times_today, details, image_path, credit, index, count,
                description=None, qr=None, reserve_bottom=0):
    """One browse page. sp = a recent_species() row; details = info.details();
    image_path None = no photo; qr = qr_images() or None;
    reserve_bottom = pixels kept free at the bottom left (button hints)."""
    width, height = size
    m = PAGE_MARGIN
    canvas = Image.new("RGB", size, COLOURS["white"])
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"

    # Photo and credit (top left)
    k = min(width / 600, height / 400)        # bigger photo on bigger screens
    pw, ph = int(PHOTO_SIZE[0] * k), int(PHOTO_SIZE[1] * k)
    x_text = m
    if image_path:
        try:
            img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
            canvas.paste(ImageOps.fit(img, (pw, ph), method=Image.LANCZOS), (m, m))
            if credit:
                for i, line in enumerate(screen.wrap(d, credit, _font("tiny"), pw)[:2]):
                    d.text((m, m + ph + 3 + i * 12), line, font=_font("tiny"),
                           fill=COLOURS["black"])
            x_text = m + pw + 18
        except Exception:
            pass

    # Names, order, family (top right)
    max_w = width - x_text - m
    y = m
    for line in screen.wrap(d, sp["Com_Name"], _font("name"), max_w)[:2]:
        d.text((x_text, y), line, font=_font("name"), fill=COLOURS["black"])
        y += 31
    d.text((x_text, y), sp["Sci_Name"], font=_font("sci"), fill=COLOURS["black"])
    y += 25

    for key in ("order", "family"):
        if details.get(key):
            text = details[key]
            label_w = d.textlength(key.upper() + ": ", font=_font("body"))
            d.text((x_text, y), key.upper() + ":", font=_font("body"), fill=COLOURS["blue"])
            d.text((x_text + label_w, y), text, font=_font("body"), fill=COLOURS["black"])
            y += 19
    y += 6

    # When heard, and the page counter
    total = sp["total"]
    total_text = f"{total} detection{'s' if total != 1 else ''} in total"
    if times_today:
        n = len(times_today)
        line1 = f"Heard {n} time{'s' if n != 1 else ''} today  •  {total} in total"
        line2 = f"First {times_today[0]}  •  Last {times_today[-1]}"
    else:
        last = datetime.strptime(sp["last_heard"][:16], "%Y-%m-%d %H:%M")
        line1 = "Last heard " + last.strftime("%d %b, %H:%M")
        line2 = total_text
    d.text((x_text, y), line1, font=_font("bold"), fill=COLOURS["red"])
    y += 20
    d.text((x_text, y), line2, font=_font("small"), fill=COLOURS["black"])

    nav = f"{index + 1} of {count}"
    nav_w = d.textlength(nav, font=_font("small"))
    if d.textlength(line2, font=_font("small")) + 20 + nav_w > max_w:
        y += 18                               # no room beside it: own line
    d.text((width - m - nav_w, y), nav, font=_font("small"), fill=COLOURS["black"])
    y += 18

    if times_today and y < 180 * k:           # room above the tiles
        recent = times_today[-TIMES_SHOWN:]
        label = "Recent: " if len(times_today) > TIMES_SHOWN else "Times: "
        d.text((x_text, y), screen.wrap(d, label + "  ".join(recent), _font("small"), max_w)[0],
               font=_font("small"), fill=COLOURS["black"])
        y += 18

    # Tiles: 5 equal columns
    tile_top = max(m + ph + 30, min(y + 10, int(232 * k)))
    col_w = (width - 2 * m) / 5
    status = details.get("uk_status") or "Not assessed"
    tiles = [(label, details.get(key) or "-", bg, fg) for key, label, bg, fg in TILES]
    tiles.append(("UK status", status) + UK_STATUS_COLOURS.get(status, (COLOURS["white"], COLOURS["black"])))
    for i, (label, value, bg, fg) in enumerate(tiles):
        bottom = draw_tile(d, m + col_w * i + 3, m + col_w * (i + 1) - 3, tile_top, label, value, bg, fg)

    # Weight
    ty = bottom + 8
    weight = weight_text(details.get("mass_g"))
    if weight:
        d.text((m, ty), weight, font=_font("bold"), fill=COLOURS["black"])
        ty += 22

    # QR code bottom right; description beside it
    qr_w = place_qr(canvas, qr, width - m, ty, height - 8)
    text_w = width - 2 * m - (qr_w + QR_GAP if qr_w else 0)
    if description:
        line_h = 18
        room = (height - m - reserve_bottom - ty) // line_h
        for line in _wrap_limit(d, description, _font("body"), text_w, min(DESCRIPTION_LINES, room)):
            d.text((m, ty), line, font=_font("body"), fill=COLOURS["black"])
            ty += line_h

    return canvas
