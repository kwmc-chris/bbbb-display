"""The full display: three screens, changed with the buttons.

    live     the latest bird, with today's totals (redraws when a new bird is heard)
    browse   a page per bird, most recent first (browse.py)
    chart    today's birds hour by hour (chart.py)

Button jobs (pins are set in settings.toml):
    browse   first press: the most recent bird, then each press goes one further back
    live     back to the live screen (it also goes back by itself after a while)
    chart    today's chart
    song     play or stop the song of the bird on screen (live or browse; needs a speaker)
    hold the SHUTDOWN buttons to show "Sleeping since..." and shut down
"""

import os
import socket
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageOps

from common import birdnet, birdsong, buttons, log_error, photos, screen
from full import browse, chart, info

HERE = os.path.dirname(os.path.abspath(__file__))

# Settings - any of these can be changed for one Pi under [full] in settings.toml
ROTATE = 0                      # 180 if the screen is mounted upside down
SATURATION = 0.5                # photo colour strength, 0-1
POLL_SECONDS = 30               # how often to check for a new bird
MIN_REFRESH_SECONDS = 180       # shortest gap between live redraws (a redraw takes ~25 s)
BROWSE_TIMEOUT_SECONDS = 300    # back to live after this long without a press
CHART_STYLE = "drawn"           # "drawn", or "birdnet" for BirdNET-Pi's own chart picture
SHOW_QR = True                  # QR code to Wikipedia on browse pages
SHOW_HINTS = True               # button letters and jobs along the bottom
SLEEP_TEXT = "Sleeping since %H:%M"     # shown after shutting down (%H hour, %M minute)
NO_PHOTO = os.path.join(HERE, "nophoto.jpg")

MARGIN = 16
LIVE_DESCRIPTION_LINES = 3
LIVE_RECENT_SPECIES = 4         # "Also heard recently" list length
FONTS = {
    "name": ("DejaVuSans-Bold.ttf", 30),
    "sci": ("DejaVuSans-Oblique.ttf", 18),
    "description": ("DejaVuSans.ttf", 15),
    "body": ("DejaVuSans.ttf", 18),
    "small": ("DejaVuSans.ttf", 16),
    "heading": ("DejaVuSans-Bold.ttf", 16),
    "credit": ("DejaVuSans.ttf", 11),
    "hint_key": ("DejaVuSans-Bold.ttf", 11),
    "hint": ("DejaVuSans.ttf", 13),
}
HINTS = {                       # (button job, label) shown on each screen
    "live": [("browse", "browse"), ("chart", "data"), ("song", "birdsong")],
    "browse": [("browse", "next"), ("live", "live"), ("chart", "data"), ("song", "birdsong")],
    "chart": [("browse", "browse"), ("live", "live")],
}
HINT_ROW = 20                   # height kept free for the hints
COLOURS = {                     # the screen's six inks; other colours come out speckled
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
}


def font(key):
    return screen.font(*FONTS[key])


def ip_address():
    """This Pi's address on the local network, or None. (Nothing is sent.)"""
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


def draw_hints(canvas, page, x, y, align="left"):
    """e.g. [A] browse  [C] data, with (x, y) the top left (or top right)."""
    items = hints(page)
    if not items:
        return
    d = ImageDraw.Draw(canvas)
    d.fontmode = "1"
    box, gap = 15, 12
    total = sum(box + 4 + d.textlength(label, font=font("hint")) + gap for _, label in items) - gap
    if align == "right":
        x -= total
    for key, label in items:
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
    d.fontmode = "1"                 # no smoothing: crisp text on e-ink

    if credit:
        d.rectangle((0, height - 18, half, height), fill=COLOURS["black"])
        d.text((6, height - 15), screen.shorten(d, credit, font("credit"), half - 12),
               font=font("credit"), fill=COLOURS["white"])

    x, y, max_w = half + m, m, half - 2 * m        # y = how far down the text has got
    for line in screen.wrap(d, det["Com_Name"], font("name"), max_w)[:2]:
        d.text((x, y), line, font=font("name"), fill=COLOURS["red"])
        y += 36
    for line in screen.wrap(d, det["Sci_Name"], font("sci"), max_w)[:2]:
        d.text((x, y), line, font=font("sci"), fill=COLOURS["black"])
        y += 24
    y += 4
    d.line((x, y, x + max_w, y), fill=COLOURS["red"], width=3)
    y += 10

    if description:
        for line in screen.wrap(d, description, font("description"), max_w)[:LIVE_DESCRIPTION_LINES]:
            d.text((x, y), line, font=font("description"), fill=COLOURS["black"])
            y += 19
        y += 8

    heard = f"Heard at {det['Time'][:5]}  •  {round(float(det['Confidence']) * 100)}% sure"
    for line in screen.wrap(d, heard, font("body"), max_w):
        d.text((x, y), line, font=font("body"), fill=COLOURS["black"])
        y += 24
    today = f"Today: {total} detections, {species} species"
    f_today = font("body") if d.textlength(today, font=font("body")) <= max_w else font("small")
    for line in screen.wrap(d, today, f_today, max_w):
        d.text((x, y), line, font=f_today, fill=COLOURS["blue"])
        y += 24
    y += 6

    others = [n for n in recent if n != det["Com_Name"]][:LIVE_RECENT_SPECIES]
    if others:
        d.text((x, y), "Also heard recently:", font=font("heading"), fill=COLOURS["black"])
        y += 22
        for name in others:
            if y + 20 > height - m - 22 - HINT_ROW:      # keep clear of the hints and footer
                break
            d.text((x + 8, y), f"• {name}", font=font("small"), fill=COLOURS["black"])
            y += 21

    # Footer: IP address on the left, time of this update (or "Sleeping since") on the right
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
    """Draw the live screen. Returns what was shown (date, time, bird), or None."""
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


# --- Browse and chart screens ---

def show_page(scr, species, index):
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


def show_chart(scr):
    canvas = chart.make_chart(scr.size, CHART_STYLE)
    m = chart.CHART_MARGIN
    draw_hints(canvas, "chart", canvas.width - m, canvas.height - m - 15, align="right")
    print("Showing today's chart - updating the screen")
    scr.show(canvas, ROTATE, SATURATION)


# --- Running ---

def run(scr, args):
    """args from start.py: once, bird, page, preview."""
    if args.page == "chart":
        return show_chart(scr)
    if args.page == "sleep":
        return show_live(scr, sleeping=datetime.now())
    if args.page == "browse" or args.bird:
        species = [browse.one_species(args.bird)] if args.bird else browse.recent_species()
        if not species or not species[0]:
            return print(f"{args.bird or 'No birds'} - not in the database")
        return show_page(scr, species, 0)
    if args.once or args.preview:
        return show_live(scr)

    global SHOW_HINTS
    btns = None
    if buttons.ENABLED:
        try:
            btns = buttons.Buttons()
            print("Buttons ready: " + ", ".join(f"{job} = GPIO {pin}" for job, pin in buttons.PINS.items()))
        except Exception as e:
            print(f"Buttons not available, so the live screen only ({e})")
            SHOW_HINTS = False

    page = "live"                 # "live", "browse" or "chart"
    shown = None                  # bird on the live screen
    last_draw = last_press = 0.0
    species, index = [], 0

    print("Watching for new birds")
    first = True
    while True:
        if first:                 # draw the live screen straight away
            presses, first = [], False
        else:
            presses = btns.wait(POLL_SECONDS) if btns else (time.sleep(POLL_SECONDS) or [])
        try:
            if btns and btns.shutdown_held(presses):
                birdsong.stop()
                print("Shutdown buttons held - showing the sleeping screen, then shutting down")
                show_live(scr, sleeping=datetime.now())
                scr.finish()          # let the sleeping screen finish drawing first
                if buttons.shutdown():
                    return
                page, shown, last_draw = "live", None, 0.0       # refused: carry on
                continue

            if "chart" in presses:
                birdsong.stop()
                page, last_press = "chart", time.time()
                show_chart(scr)
                continue

            if "live" in presses and page != "live":
                birdsong.stop()
                page = "live"
                shown, last_draw = show_live(scr), time.time()
                btns.clear()          # ignore presses made during the redraw
                continue

            steps = presses.count("browse")
            if steps:
                birdsong.stop()
                if page != "browse":  # first press: the most recent bird
                    species, index, page = browse.recent_species(), 0, "browse"
                    steps -= 1
                if species:
                    index = (index + steps) % len(species)      # back to the start after the last
                    if "song" in presses:                       # start the song before the slow redraw
                        birdsong.toggle(species[index]["Com_Name"])
                    show_page(scr, species, index)
                last_press = time.time()
                continue

            if "song" in presses:      # the bird on screen: browse page, or the live screen
                if page == "browse" and species:
                    birdsong.toggle(species[index]["Com_Name"])
                    last_press = time.time()
                elif page == "live" and shown:
                    birdsong.toggle(shown[2])
                continue

            if page != "live":
                if time.time() - last_press >= BROWSE_TIMEOUT_SECONDS:
                    print("No presses for a while - back to the live screen")
                    birdsong.stop()
                    page = "live"
                    shown, last_draw = show_live(scr), time.time()
                continue

            det = birdnet.latest()
            if det and (det["Date"], det["Time"], det["Com_Name"]) != shown \
                    and time.time() - last_draw >= MIN_REFRESH_SECONDS:
                shown, last_draw = show_live(scr), time.time()
        except Exception:
            log_error()
