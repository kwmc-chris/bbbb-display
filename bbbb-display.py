#!/usr/bin/env python3
"""
bbbb-display.py - main script for the BirdNET-Pi Inky Impression display.

Watches BirdNET-Pi's database and shows birds on the e-ink screen.
Three screens:
    LIVE    latest bird heard (default; redraws when a new bird is heard)
    BROWSE  one page per species, most recent first
    DATA    today's species-by-hour chart
Buttons (hints are shown on each screen):
    A  browse: first press = most recent species, each further press = next older
    B  back to LIVE (also after BROWSE_TIMEOUT_SECONDS without a press)
    C  DATA screen (pressed there: redraw)
    D  play / stop the birdsong of the species on screen (BROWSE only)
    A + D held for SHUTDOWN_HOLD_SECONDS: show "Sleeping since ..." and power off

Helper files (same folder): birdinfo.py, birdbrowser.py, birdchart.py, birdqr.py,
birdsong.py.

Run (in the Pimoroni environment):
    python3 bbbb-display.py            run normally
    python3 bbbb-display.py --help     list all options
    --once / --browse N / --chart           draw one screen and exit
    --sleep-screen                          draw the "sleeping" screen (no shutdown)
    --preview file.png                      save a PNG instead of using the screen

Sections: 1 Settings, 2 Imports, 3 Helpers, 4 Database, 5 Live screen,
          6 Showing screens, 7 Command line, 8 Main loop
"""

# =============================================================================
# 1. SETTINGS   ([--option] = can also be set on the command line)
# =============================================================================

import os

HOME = os.path.expanduser("~")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Helper file names (without .py)
INFO_MODULE = "birdinfo"
BROWSER_MODULE = "birdbrowser"
CHART_MODULE = "birdchart"
QR_MODULE = "birdqr"
SONG_MODULE = "birdsong"

# Files and folders
DATABASE = os.path.join(HOME, "BirdNET-Pi", "scripts", "birds.db")   # [--db]
DEFAULT_IMAGE = os.path.join(SCRIPT_DIR, "imagetest.jpg")             # [--image]
SPECIES_IMAGE_DIR = os.path.join(SCRIPT_DIR, "birds")                 # [--image-dir] your own photos, e.g. "European Robin.jpg"

# Timing (seconds)
POLL_SECONDS = 30                # check for new birds              [--poll]
MIN_REFRESH_SECONDS = 180        # min gap between live redraws     [--min-refresh]
BROWSE_TIMEOUT_SECONDS = 300     # idle time before back to LIVE    [--browse-timeout]

# Screen
SATURATION = 0.5                 # photo colour strength 0-1        [--saturation]
ROTATE = 0                       # 180 if mounted upside down       [--rotate]
MARGIN = 16                      # live screen edge gap (px)        [--margin]
PREVIEW_SIZE = (600, 400)        # size used for --preview
CHART_STYLE = "drawn"            # "drawn" or "birdnet" (BirdNET-Pi's image) [--chart-style]
SHOW_QR = True                   # QR code to Wikipedia on browse pages    [--no-qr]

# Button hints shown on each screen: (button, label)
SHOW_BUTTON_HINTS = True
BUTTON_HINTS = {
    "live": [("A", "browse"), ("C", "data")],
    "browse": [("A", "next"), ("B", "live"), ("C", "data"), ("D", "birdsong")],
    "chart": [("A", "browse"), ("B", "live")],
}
HINT_FONTS = {"key": ("DejaVuSans-Bold.ttf", 11), "label": ("DejaVuSans.ttf", 13)}
HINT_ROW = 20                    # height kept free for the hints (px)

# Power off: hold A and D together. The live screen then shows SLEEP_TEXT
# (time codes: %H hour, %M minute, %d day, %b month) and the Pi shuts down.
SHUTDOWN_ENABLED = True
SHUTDOWN_HOLD_SECONDS = 3
SLEEP_TEXT = "Sleeping since %H:%M"
SHUTDOWN_COMMAND = ["sudo", "-n", "shutdown", "-h", "now"]

# Log
LOG_TIMESTAMPS = True            # start each printed line with date/time
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# Live screen layout
LIVE_DESCRIPTION_LINES = 3
LIVE_RECENT_SPECIES = 4          # "Also heard recently" list length
LIVE_FONTS = {                   # (font file, size)
    "name": ("DejaVuSans-Bold.ttf", 30),
    "sci": ("DejaVuSans-Oblique.ttf", 18),
    "description": ("DejaVuSans.ttf", 15),
    "body": ("DejaVuSans.ttf", 18),
    "small": ("DejaVuSans.ttf", 16),
    "heading": ("DejaVuSans-Bold.ttf", 16),
    "credit": ("DejaVuSans.ttf", 11),
}
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

# The screen's six inks. Other colours are dithered (speckled).
COLOURS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}

# =============================================================================
# 2. IMPORTS
# =============================================================================

import argparse
import importlib
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps


class TimestampedOutput:
    """Prefixes each printed line with the date and time."""

    def __init__(self, stream):
        self._stream = stream
        self._at_line_start = True

    def write(self, text):
        out = []
        for piece in text.splitlines(keepends=True):
            if self._at_line_start:
                out.append(datetime.now().strftime(TIMESTAMP_FORMAT) + "  ")
            out.append(piece)
            self._at_line_start = piece.endswith("\n")
        self._stream.write("".join(out))
        self._stream.flush()
        return len(text)

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


if LOG_TIMESTAMPS and __name__ == "__main__" and not hasattr(sys.stdout, "_at_line_start"):
    sys.stdout = TimestampedOutput(sys.stdout)       # (not if already wrapped)
    sys.stderr = TimestampedOutput(sys.stderr)


def load_helper(name):
    """Import a helper file; returns None (feature skipped) if it fails."""
    try:
        return importlib.import_module(name)
    except Exception as e:
        print(f"Couldn't load {name}.py ({e}) - continuing without it.")
        return None


birdinfo = load_helper(INFO_MODULE)
birdbrowser = load_helper(BROWSER_MODULE)
birdchart = load_helper(CHART_MODULE)
birdqr = load_helper(QR_MODULE)
birdsong = load_helper(SONG_MODULE)

# =============================================================================
# 3. HELPERS
# =============================================================================

def font(key_or_file, size=None):
    """A LIVE_FONTS key, or a font file + size."""
    if size is None:
        key_or_file, size = LIVE_FONTS[key_or_file]
    try:
        return ImageFont.truetype(FONT_DIR + key_or_file, size)
    except OSError:
        return ImageFont.load_default(size=size)


def wrap(draw, text, fnt, max_width):
    """Split text into lines no wider than max_width pixels."""
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


def ip_address():
    """The Pi's local IP address, or None (no data is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            return s.getsockname()[0]
    except OSError:
        return None

def draw_hints(canvas, screen, x, y, align="left"):
    """Button hints, e.g. [A] browse  [C] data. (x, y) = top-left, or
    top-right with align="right"."""
    if not SHOW_BUTTON_HINTS:
        return
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"
    f_key = font(*HINT_FONTS["key"])
    f_label = font(*HINT_FONTS["label"])
    box, gap = 15, 12                     # key box size, space between hints
    items = BUTTON_HINTS.get(screen, [])
    total = sum(box + 4 + d.textlength(label, font=f_label) for _, label in items) \
        + gap * (len(items) - 1)
    if align == "right":
        x -= total
    for key, label in items:
        d.rounded_rectangle((x, y, x + box, y + box), radius=3, fill=COLOURS["black"])
        kw = d.textlength(key, font=f_key)
        d.text((x + (box - kw) / 2, y + 1), key, font=f_key, fill=COLOURS["white"])
        x += box + 4
        d.text((x, y), label, font=f_label, fill=COLOURS["black"])
        x += d.textlength(label, font=f_label) + gap


# =============================================================================
# 4. DATABASE  (BirdNET-Pi's "detections" table, opened read-only)
# =============================================================================

def connect(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def latest_detection(db_path):
    """Most recent detection row, or None."""
    con = connect(db_path)
    try:
        return con.execute(
            "SELECT Date, Time, Com_Name, Sci_Name, Confidence FROM detections "
            "ORDER BY Date DESC, Time DESC LIMIT 1").fetchone()
    finally:
        con.close()


def today_stats(db_path, date):
    """(total detections, number of species, up to 6 recent species) for a date."""
    con = connect(db_path)
    try:
        total, species = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT Com_Name) FROM detections WHERE Date = ?",
            (date,)).fetchone()
        recent = [r[0] for r in con.execute(
            "SELECT Com_Name FROM detections WHERE Date = ? "
            "GROUP BY Com_Name ORDER BY MAX(Time) DESC LIMIT 6", (date,))]
    finally:
        con.close()
    return total, species, recent

# =============================================================================
# 5. LIVE SCREEN  (photo left, text right; y = current text height)
# =============================================================================

def render_live(size, image_path, det, total, species, recent, args,
                description=None, credit=None, sleeping_since=None):
    width, height = size
    half = width // 2
    m = args.margin
    canvas = Image.new("RGB", size, COLOURS["white"])

    # Photo, cropped to fill the left half
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    canvas.paste(ImageOps.fit(img, (half, height), method=Image.LANCZOS), (0, 0))

    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"                 # no anti-aliasing: crisp text on e-ink

    if credit:
        d.rectangle((0, height - 18, half, height), fill=COLOURS["black"])
        d.text((6, height - 15), credit[:55], font=font("credit"), fill=COLOURS["white"])

    x, y, max_w = half + m, m, half - 2 * m

    for line in wrap(d, det["Com_Name"], font("name"), max_w)[:2]:
        d.text((x, y), line, font=font("name"), fill=COLOURS["red"])
        y += 36
    for line in wrap(d, det["Sci_Name"], font("sci"), max_w)[:2]:
        d.text((x, y), line, font=font("sci"), fill=COLOURS["black"])
        y += 24

    y += 4
    d.line((x, y, x + max_w, y), fill=COLOURS["red"], width=3)
    y += 10

    if description:
        for line in wrap(d, description, font("description"), max_w)[:LIVE_DESCRIPTION_LINES]:
            d.text((x, y), line, font=font("description"), fill=COLOURS["black"])
            y += 19
        y += 8

    heard_time = det["Time"][:5]
    confidence = round(float(det["Confidence"]) * 100)
    for line in wrap(d, f"Heard at {heard_time}  •  {confidence}% sure", font("body"), max_w):
        d.text((x, y), line, font=font("body"), fill=COLOURS["black"])
        y += 24

    # Smaller font if it won't fit on one line
    today = f"Today: {total} detections, {species} species"
    f_today = font("body") if d.textlength(today, font=font("body")) <= max_w else font("small")
    for line in wrap(d, today, f_today, max_w):
        d.text((x, y), line, font=f_today, fill=COLOURS["blue"])
        y += 24
    y += 6

    others = [n for n in recent if n != det["Com_Name"]][:LIVE_RECENT_SPECIES]
    if others:
        d.text((x, y), "Also heard recently:", font=font("heading"), fill=COLOURS["black"])
        y += 22
        for name in others:
            if y + 20 > height - m - 22 - HINT_ROW:     # keep clear of hints + footer
                break
            d.text((x + 8, y), f"• {name}", font=font("small"), fill=COLOURS["black"])
            y += 21

    # Footer: IP address left, update time right
    footer_y = height - m - 16
    if not sleeping_since:                    # no IP address once it's off
        ip = ip_address()
        d.text((x, footer_y), f"IP {ip}" if ip else "No network", font=font("small"),
               fill=COLOURS["black"])
    # Bottom right: update time, or "Sleeping since ..." when powering off
    if sleeping_since:
        status, colour = sleeping_since.strftime(SLEEP_TEXT), COLOURS["red"]
    else:
        status, colour = datetime.now().strftime("Updated %H:%M"), COLOURS["green"]
    w = d.textlength(status, font=font("small"))
    d.text((width - m - w, footer_y), status, font=font("small"), fill=colour)

    if not sleeping_since:                    # buttons don't work while it's off
        draw_hints(canvas, "live", x, footer_y - HINT_ROW - 4)
    return canvas

# =============================================================================
# 6. SHOWING SCREENS
# =============================================================================

def find_own_photo(image_dir, com_name):
    """Your photo in image_dir named after the bird (spaces, _ or - all match)."""
    if not image_dir or not os.path.isdir(image_dir):
        return None
    wanted = {com_name.lower(), com_name.lower().replace(" ", "_"),
              com_name.lower().replace(" ", "-")}
    for f in os.listdir(image_dir):
        stem, ext = os.path.splitext(f)
        if stem.lower() in wanted and ext.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
            return os.path.join(image_dir, f)
    return None


def species_image(com_name, sci_name, args):
    """(photo path, credit): your photo > downloaded photo > default image."""
    image, credit = find_own_photo(args.image_dir, com_name), None
    if not image and birdinfo and not args.no_web_image:
        try:
            image, credit = birdinfo.get_image(com_name, sci_name)
        except Exception as e:
            print(f"Couldn't get photo: {e}")
    return image or args.image, credit


def screen_size(display):
    return display.resolution if display else PREVIEW_SIZE


def show(display, canvas, args):
    """Send to the e-ink (~25 s), or save a PNG with --preview."""
    if args.rotate:
        canvas = canvas.rotate(args.rotate)
    if display is None:
        canvas.save(args.preview)
        print(f"Preview saved to {args.preview}")
        return
    try:
        display.set_image(canvas, saturation=args.saturation)
    except TypeError:                    # driver without saturation
        display.set_image(canvas)
    display.show()


def show_live(display, args, sleeping_since=None):
    """Draw LIVE. Returns (date, time, name) of the bird shown, or None."""
    det = latest_detection(args.db)
    if det is None:
        print("No detections in the database yet.")
        return None
    total, species, recent = today_stats(args.db, det["Date"])
    image, credit = species_image(det["Com_Name"], det["Sci_Name"], args)

    description = None
    if birdinfo and not args.no_description:
        try:
            description = birdinfo.get_description(det["Com_Name"], det["Sci_Name"])
        except Exception as e:
            print(f"Couldn't get description: {e}")

    canvas = render_live(screen_size(display), image, det, total, species, recent, args,
                         description, credit, sleeping_since)
    print(f"{det['Time']}  {det['Com_Name']} - updating screen...")
    show(display, canvas, args)
    return (det["Date"], det["Time"], det["Com_Name"])


def show_species_page(display, args, species_list, index):
    """Draw BROWSE page `index` of species_list."""
    sp = species_list[index]
    today = datetime.now().strftime("%Y-%m-%d")
    times = birdbrowser.species_times(args.db, sp["Com_Name"], today)

    details, description, source_url = {}, None, None
    if birdinfo:
        try:
            details = birdinfo.get_details(sp["Com_Name"], sp["Sci_Name"])
            description = birdinfo.get_description(sp["Com_Name"], sp["Sci_Name"],
                                                   sentences=4, max_chars=600)
            if SHOW_QR and birdqr and not args.no_qr:
                source_url = birdinfo.get_source_url(sp["Com_Name"], sp["Sci_Name"])
        except Exception as e:
            print(f"Couldn't get details: {e}")

    image, credit = species_image(sp["Com_Name"], sp["Sci_Name"], args)
    if image == args.image:
        image = None                     # no real photo: page uses the space for text

    canvas = birdbrowser.render_page(screen_size(display), sp, times, details, image,
                                     credit, index, len(species_list),
                                     description=description,
                                     qr_images=birdqr.qr_images(source_url) if source_url else None,
                                     reserve_bottom=HINT_ROW if SHOW_BUTTON_HINTS else 0)
    m = birdbrowser.PAGE_MARGIN
    draw_hints(canvas, "browse", m, canvas.height - m - 15)
    print(f"Browsing {index + 1}/{len(species_list)}: {sp['Com_Name']} - updating screen...")
    show(display, canvas, args)


def show_chart(display, args):
    canvas = birdchart.make_chart(screen_size(display), args.db, args.chart_style)
    m = birdchart.CHART_MARGIN
    draw_hints(canvas, "chart", canvas.width - m, canvas.height - m - 15, align="right")
    print("Showing today's chart - updating screen...")
    show(display, canvas, args)

def play_song(args, sp):
    """Button D: play (or stop) the birdsong for species sp."""
    if birdsong:
        try:
            birdsong.toggle(args.db, sp["Com_Name"])
        except Exception as e:
            print(f"Couldn't play birdsong: {e}")
    else:
        print("birdsong.py not loaded - can't play birdsong.")


def stop_song():
    if birdsong:
        birdsong.stop()


def power_off(display, args):
    """A + D held: show "Sleeping since ..." on the live screen, then shut down.
    The screen keeps its picture with the power off. Returns False if the
    shutdown was refused."""
    stop_song()
    now = datetime.now()
    print("A + D held - showing the sleeping screen, then shutting down.")
    show_live(display, args, sleeping_since=now)       # waits until drawn
    result = subprocess.run(SHUTDOWN_COMMAND, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Shutdown failed ({result.stderr.strip() or result.returncode}) - "
              f"check 'sudo -n shutdown' works for this user. Carrying on.")
        return False
    return True


# =============================================================================
# 7. COMMAND LINE  (defaults come from SETTINGS)
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(description="BirdNET-Pi detections on the Inky Impression")
    p.add_argument("--db", default=DATABASE, help="BirdNET-Pi's birds.db")
    p.add_argument("--image", default=DEFAULT_IMAGE, help="image when there's no bird photo")
    p.add_argument("--image-dir", default=SPECIES_IMAGE_DIR, help="folder of your own bird photos")
    p.add_argument("--poll", type=int, default=POLL_SECONDS, help="seconds between database checks")
    p.add_argument("--min-refresh", type=int, default=MIN_REFRESH_SECONDS,
                   help="min seconds between live redraws")
    p.add_argument("--browse-timeout", type=int, default=BROWSE_TIMEOUT_SECONDS,
                   help="idle seconds before returning to the live screen")
    p.add_argument("--margin", type=int, default=MARGIN, help="edge gap in pixels")
    p.add_argument("--saturation", type=float, default=SATURATION, help="photo colour 0.0-1.0")
    p.add_argument("--rotate", type=int, choices=[0, 180], default=ROTATE)
    p.add_argument("--chart-style", choices=["drawn", "birdnet"], default=CHART_STYLE)
    p.add_argument("--no-description", action="store_true", help="no description on the live screen")
    p.add_argument("--no-web-image", action="store_true", help="don't download photos")
    p.add_argument("--no-buttons", action="store_true", help="ignore the buttons")
    p.add_argument("--no-qr", action="store_true", help="no QR codes on browse pages")
    p.add_argument("--check", action="store_true", help="test the database and exit")
    p.add_argument("--once", action="store_true", help="draw the live screen once and exit")
    p.add_argument("--browse", type=int, metavar="N", help="draw browse page N and exit")
    p.add_argument("--chart", action="store_true", help="draw today's chart and exit")
    p.add_argument("--sleep-screen", action="store_true",
                   help="draw the 'sleeping' live screen and exit (doesn't shut down)")
    p.add_argument("--preview", metavar="FILE.png", help="save a PNG instead of using the screen")
    return p.parse_args()

# =============================================================================
# 8. MAIN LOOP
# =============================================================================

def main():
    print(f"===== Starting {os.path.basename(__file__)} from {SCRIPT_DIR} =====")
    args = parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"Database not found at {args.db} - use --db to set the path.")

    if args.check:
        det = latest_detection(args.db)
        print("Database OK." if det else "Database OK, but no detections yet.")
        if det:
            print(f"Latest: {det['Date']} {det['Time']} {det['Com_Name']} "
                  f"({det['Sci_Name']}) {float(det['Confidence']):.2f}")
        return

    display = None
    if not args.preview:
        from inky.auto import auto
        display = auto(ask_user=False, verbose=True)    # never prompt (boot)

    # One-off actions
    if args.chart:
        show_chart(display, args)
        return
    if args.browse is not None:
        species_list = birdbrowser.recent_species(args.db)
        if species_list:
            show_species_page(display, args, species_list, min(args.browse, len(species_list) - 1))
        return
    if args.sleep_screen:
        show_live(display, args, sleeping_since=datetime.now())
        return
    if args.once or args.preview:
        show_live(display, args)
        return

    buttons = None
    if birdbrowser and not args.no_buttons:
        try:
            buttons = birdbrowser.Buttons()
            print(f"Buttons ready ({buttons.backend}): A browse, B live, C data, D birdsong.")
        except Exception as e:
            print(f"Buttons not available, live screen only ({e})")

    mode = "live"                # "live", "browse" or "chart"
    last_shown = None            # bird on the live screen
    last_refresh = 0.0
    species_list, index = [], 0
    last_press = 0.0

    print("Watching for new detections (Ctrl+C to stop)...")
    while True:
        # Returns early on a button press, e.g. ["D", "D"]
        presses = buttons.wait(args.poll) if buttons else (time.sleep(args.poll) or [])

        try:
            # A + D held down together: power off. A quick press of either
            # is released at once, so held() returns straight away.
            if (SHUTDOWN_ENABLED and buttons and ("A" in presses or "D" in presses)
                    and buttons.held({"A", "D"}, max(0, SHUTDOWN_HOLD_SECONDS -
                                                     birdbrowser.EXTRA_PRESS_WAIT_SECONDS))):
                if power_off(display, args):
                    return
                mode, last_shown, last_refresh = "live", None, 0.0     # redraw normally
                continue

            # C: data screen (pressed there: redraw it)
            if "C" in presses and birdchart:
                stop_song()
                mode = "chart"
                show_chart(display, args)
                last_press = time.time()
                continue

            # B: back to the live screen
            if "B" in presses and mode != "live":
                stop_song()
                mode = "live"
                last_shown = show_live(display, args)
                last_refresh = time.time()
                if buttons:
                    buttons.clear()          # drop presses made during the redraw
                continue

            # A: browse. First press = most recent species; each further press = next older
            steps = presses.count("A")
            if steps:
                stop_song()
                if mode != "browse":
                    species_list = birdbrowser.recent_species(args.db)
                    index, mode = 0, "browse"
                    steps -= 1
                if species_list:
                    index = (index + steps) % len(species_list)      # wraps round to the start
                    if "D" in presses:       # D pressed too: start the song before the slow redraw
                        play_song(args, species_list[index])
                    show_species_page(display, args, species_list, index)
                last_press = time.time()
                continue

            # D: play / stop the birdsong of the species on screen (browse only)
            if "D" in presses:
                if mode == "browse" and species_list:
                    play_song(args, species_list[index])
                    last_press = time.time()
                continue

            if mode in ("browse", "chart"):
                if time.time() - last_press >= args.browse_timeout:
                    print("No button presses for a while - back to the live screen.")
                    stop_song()
                    mode = "live"
                    last_shown = show_live(display, args)
                    last_refresh = time.time()
                continue

            # LIVE: redraw for a new bird, at most every min_refresh seconds
            det = latest_detection(args.db)
            key = (det["Date"], det["Time"], det["Com_Name"]) if det else None
            due = time.time() - last_refresh >= args.min_refresh
            if key and key != last_shown and due:
                last_shown = show_live(display, args)
                last_refresh = time.time()

        except sqlite3.OperationalError as e:
            print(f"Database busy or unavailable ({e}), retrying...")


if __name__ == "__main__":
    main()
