"""The full display: the live screen and browse pages, changed with the buttons.

Button jobs (pins are set in settings.toml):
    browse   first press: the most recent bird, then one further back each press
    live     back to the live screen (also happens after BROWSE_TIMEOUT_SECONDS)
    song     play or stop the song of the bird on screen
    hold the SHUTDOWN buttons: show "Sleeping since..." and shut down
"""

import os
import socket
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageOps

from common import birdnet, birdsong, buttons, log_error, photos, screen
from full import browse, info

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Settings (change any of these under [full] in settings.toml) ---
ROTATE = 0                      # 0, or 180 if mounted upside down
SATURATION = 0.5                # photo colour strength, 0-1
POLL_SECONDS = 30               # how often to check for a new bird
MIN_REFRESH_SECONDS = 180       # shortest gap between live redraws
BROWSE_TIMEOUT_SECONDS = 300    # back to live after this long without a press
SHOW_QR = True                  # QR code to Wikipedia on browse pages
SHOW_HINTS = True               # button letters and jobs along the bottom
SLEEP_TEXT = "Sleeping since %H:%M"
NO_PHOTO = os.path.join(HERE, "nophoto.jpg")

MARGIN = 16
LIVE_DESCRIPTION_LINES = 3
LIVE_RECENT_SPECIES = 4         # length of the "Also heard recently" list
FONTS = {
    "name": ("DejaVuSans-Bold.ttf", 30),
    "sci": ("DejaVuSans-BoldOblique.ttf", 18),
    "description": ("DejaVuSans-Bold.ttf", 15),
    "body": ("DejaVuSans-Bold.ttf", 18),
    "small": ("DejaVuSans-Bold.ttf", 16),
    "heading": ("DejaVuSans-Bold.ttf", 16),
    "credit": ("DejaVuSans.ttf", 11),
    "hint_key": ("DejaVuSans-Bold.ttf", 11),
    "hint": ("DejaVuSans.ttf", 13),
}
HINTS = {                       # (button job, label) on each screen
    "live": [("browse", "browse"), ("song", "birdsong")],
    "browse": [("browse", "next"), ("live", "live"), ("song", "birdsong")],
}
HINT_ROW = 20                   # height kept free for the hints
COLOURS = {                     # the screen's six inks
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}


# --- Helpers ---

def font(key):
    return screen.font(*FONTS[key])


def fit(d, text, font_spec, width):
    """The font at its size, or smaller (down to 12), so text fits on one line."""
    name, size = font_spec
    while size > 12 and d.textlength(text, font=screen.font(name, size)) > width:
        size -= 1
    return screen.font(name, size)


def ip_address():
    """This Pi's address on the local network, or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def hints(page):
    """[(letter, label)] for the buttons that work on this page."""
    if not SHOW_HINTS:
        return []
    return [(buttons.letter(job), label) for job, label in HINTS[page]
            if buttons.letter(job) and (job != "song" or birdsong.enabled())]


def draw_hints(canvas, page, x, y):
    """Button hints, e.g. [A] browse  [D] birdsong, starting at (x, y)."""
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"
    box, gap = 15, 12
    for key, label in hints(page):
        d.rounded_rectangle((x, y, x + box, y + box), radius=3, fill=COLOURS["black"])
        d.text((x + (box - d.textlength(key, font=font("hint_key"))) / 2, y + 1), key,
               font=font("hint_key"), fill=COLOURS["white"])
        x += box + 4
        d.text((x, y), label, font=font("hint"), fill=COLOURS["black"])
        x += d.textlength(label, font=font("hint")) + gap


# --- Live screen: photo on the left, text on the right ---

def render_live(size, photo, credit, det, description, total, species, recent, sleeping=None):
    width, height = size
    half, m = width // 2, MARGIN
    canvas = Image.new("RGB", size, COLOURS["white"])
    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    canvas.paste(ImageOps.fit(img, (half, height), method=Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"

    # Photo credit along the bottom of the photo
    if credit:
        d.rectangle((0, height - 18, half, height), fill=COLOURS["black"])
        d.text((6, height - 15), screen.shorten(d, credit, font("credit"), half - 12),
               font=font("credit"), fill=COLOURS["white"])

    # Names (y = how far down the text has got)
    x, y, max_w = half + m, m, half - 2 * m
    for line in screen.wrap(d, det["Com_Name"], font("name"), max_w)[:2]:
        d.text((x, y), line, font=font("name"), fill=COLOURS["red"])
        y += 36
    for line in screen.wrap(d, det["Sci_Name"], font("sci"), max_w)[:2]:
        d.text((x, y), line, font=font("sci"), fill=COLOURS["black"])
        y += 24
    y += 4
    d.line((x, y, x + max_w, y), fill=COLOURS["red"], width=3)
    y += 10

    # Description
    if description:
        for line in screen.wrap(d, description, font("description"), max_w)[:LIVE_DESCRIPTION_LINES]:
            d.text((x, y), line, font=font("description"), fill=COLOURS["black"])
            y += 19
        y += 8

    # When heard, and today's totals (smaller if needed to fit on one line)
    heard = f"Heard at {det['Time'][:5]}  •  {round(float(det['Confidence']) * 100)}% sure"
    today = f"Today: {total} detections, {species} species"
    for text, colour in ((heard, COLOURS["black"]), (today, COLOURS["blue"])):
        d.text((x, y), text, font=fit(d, text, FONTS["body"], max_w), fill=colour)
        y += 24
    y += 6

    # Other birds heard recently
    others = [n for n in recent if n != det["Com_Name"]][:LIVE_RECENT_SPECIES]
    if others:
        d.text((x, y), "Also heard recently:", font=font("heading"), fill=COLOURS["black"])
        y += 22
        for name in others:
            if y + 20 > height - m - 22 - HINT_ROW:
                break
            d.text((x + 8, y), f"• {name}", font=font("small"), fill=COLOURS["black"])
            y += 21

    # Footer: IP address left, update time (or "Sleeping since") right
    footer_y = height - m - 16
    if sleeping:
        status, colour = sleeping.strftime(SLEEP_TEXT), COLOURS["red"]
    else:
        ip = ip_address()
        d.text((x, footer_y), f"IP {ip}" if ip else "No network", font=font("small"),
               fill=COLOURS["black"])
        status, colour = datetime.now().strftime("Updated %H:%M"), COLOURS["green"]
        draw_hints(canvas, "live", x, footer_y - HINT_ROW - 4)
    d.text((width - m - d.textlength(status, font=font("small")), footer_y), status,
           font=font("small"), fill=colour)
    return canvas


def show_live(scr, sleeping=None):
    """Draw the live screen. Returns (date, time, bird) shown, or None."""
    det = birdnet.latest()
    if det is None:
        print("No birds in the database yet.")
        return None
    rows = birdnet.query("SELECT COUNT(*), COUNT(DISTINCT Com_Name) FROM detections WHERE Date = ?",
                         det["Date"])
    recent = [r[0] for r in birdnet.query("SELECT Com_Name FROM detections WHERE Date = ? "
                                          "GROUP BY Com_Name ORDER BY MAX(Time) DESC LIMIT 6",
                                          det["Date"])]
    photo, credit = photos.get_photo(det["Com_Name"], det["Sci_Name"])
    description = info.description(det["Com_Name"], det["Sci_Name"])
    print(f"{det['Time']}  {det['Com_Name']} - updating the screen")
    canvas = render_live(scr.size, photo or NO_PHOTO, credit, det, description,
                         rows[0][0], rows[0][1], recent, sleeping)
    scr.show(canvas, ROTATE, SATURATION)
    return (det["Date"], det["Time"], det["Com_Name"])


# --- Browse page ---

def show_page(scr, species, index):
    """Draw the browse page for species[index]."""
    sp = species[index]
    times = browse.times_heard(sp["Com_Name"], datetime.now().strftime("%Y-%m-%d"))
    details = info.details(sp["Com_Name"], sp["Sci_Name"])
    description = info.description(sp["Com_Name"], sp["Sci_Name"], sentences=4, max_chars=600)
    link = info.wiki_link(sp["Com_Name"], sp["Sci_Name"]) if SHOW_QR else None
    photo, credit = photos.get_photo(sp["Com_Name"], sp["Sci_Name"])

    canvas = browse.render_page(scr.size, sp, times, details, photo, credit, index, len(species),
                                description=description, qr=browse.qr_images(link) if link else None,
                                reserve_bottom=HINT_ROW if hints("browse") else 0)
    m = browse.PAGE_MARGIN
    draw_hints(canvas, "browse", m, canvas.height - m - 15)
    print(f"Browsing {index + 1} of {len(species)}: {sp['Com_Name']} - updating the screen")
    scr.show(canvas, ROTATE, SATURATION)


# --- Running ---

def run(scr, args):
    """args from start.py: once, bird, page, preview."""
    # One picture, then stop
    if args.page == "sleep":
        return show_live(scr, sleeping=datetime.now())
    if args.page == "browse" or args.bird:
        species = [browse.one_species(args.bird)] if args.bird else browse.recent_species()
        if not species or not species[0]:
            return print(f"{args.bird or 'No birds'} - not in the database")
        return show_page(scr, species, 0)
    if args.once or args.preview:
        return show_live(scr)

    # Buttons
    global SHOW_HINTS
    btns = None
    if buttons.ENABLED:
        try:
            btns = buttons.Buttons()
            print("Buttons ready: " + ", ".join(f"{job} = GPIO {pin}" for job, pin in buttons.PINS.items()))
        except Exception as e:
            print(f"Buttons not available, so the live screen only ({e})")
            SHOW_HINTS = False

    page = "live"                 # "live" or "browse"
    shown = None                  # (date, time, bird) on the live screen
    last_draw = last_press = 0.0
    species, index = [], 0

    print("Watching for new birds")
    first = True
    while True:
        # Wait for a button press or POLL_SECONDS (no wait the first time)
        if first:
            presses, first = [], False
        else:
            presses = btns.wait(POLL_SECONDS) if btns else (time.sleep(POLL_SECONDS) or [])
        try:
            # Shutdown buttons held: sleeping screen, then shut down
            if btns and btns.shutdown_held(presses):
                birdsong.stop()
                print("Shutdown buttons held - showing the sleeping screen, then shutting down")
                show_live(scr, sleeping=datetime.now())
                if buttons.shutdown():
                    return
                page, shown, last_draw = "live", None, 0.0
                continue

            # Live button
            if "live" in presses and page != "live":
                birdsong.stop()
                page = "live"
                shown, last_draw = show_live(scr), time.time()
                btns.clear()
                continue

            # Browse button: most recent bird first, then one further back each press
            steps = presses.count("browse")
            if steps:
                birdsong.stop()
                if page != "browse":
                    species, index, page = browse.recent_species(), 0, "browse"
                    steps -= 1
                if species:
                    index = (index + steps) % len(species)
                    if "song" in presses:
                        birdsong.toggle(species[index]["Com_Name"])
                    show_page(scr, species, index)
                last_press = time.time()
                continue

            # Song button: the bird on screen
            if "song" in presses:
                if page == "browse" and species:
                    birdsong.toggle(species[index]["Com_Name"])
                    last_press = time.time()
                elif page == "live" and shown:
                    birdsong.toggle(shown[2])
                continue

            # Browsing: back to live after BROWSE_TIMEOUT_SECONDS without a press
            if page != "live":
                if time.time() - last_press >= BROWSE_TIMEOUT_SECONDS:
                    print("No presses for a while - back to the live screen")
                    birdsong.stop()
                    page = "live"
                    shown, last_draw = show_live(scr), time.time()
                continue

            # Live: redraw for a new bird, at most every MIN_REFRESH_SECONDS
            det = birdnet.latest()
            if det and (det["Date"], det["Time"], det["Com_Name"]) != shown \
                    and time.time() - last_draw >= MIN_REFRESH_SECONDS:
                shown, last_draw = show_live(scr), time.time()
        except Exception:
            log_error()
