"""The simple display, in portrait: the latest bird's everyday name (Robin, not
European Robin), its photo across the width, and a verse from a classic poem
that mentions it - a different verse each time.

Button jobs (pins are set in common/buttons.py):
    browse   first press: the most recent bird, then one further back each press
    live     back to the live screen (also happens after BROWSE_TIMEOUT_SECONDS)
    song     play or stop the song of the bird on screen
    hold the SHUTDOWN buttons: show "Sleeping since..." and shut down
"""

import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageOps

from common import bird_info, birdnet, birdsong, buttons, log_error, photos, screen, status
from simple import poems

# --- Settings (change any of these under [simple] in settings.toml) ---
ROTATE = 90                 # 90 or 270, depending which way up the screen is
SATURATION = 0.5            # photo colour strength, 0-1
POLL_SECONDS = 30           # how often to check for a new bird
MIN_REFRESH_SECONDS = 180   # shortest gap between redraws
BROWSE_TIMEOUT_SECONDS = 300    # back to live after this long without a press
RECENT_SPECIES_LIMIT = 30   # birds in the browse list
HEARD_TEXT = "Heard %a %H:%M"   # when a browsed bird was last heard, e.g. "Heard Mon 18:22"
PHOTO_MAX_SHARE = 0.6       # most of the screen height a tall photo may take
SHOW_FOOTER = True          # IP address and update time along the bottom (always shows "Sleeping since")
MARGIN = 16
NAME_FONT = "DejaVuSans-Bold.ttf"
VERSE_FONT = "DejaVuSans-Bold.ttf"
SMALL_FONT = "DejaVuSans.ttf"
HINT_KEY_FONT = "DejaVuSans-Bold.ttf"
HINT_FONT = "DejaVuSans.ttf"
HINTS = {                   # (button job, label) on each screen
    "live": [("browse", "browse"), ("song", "birdsong")],
    "browse": [("browse", "next"), ("live", "live"), ("song", "birdsong")],
}
DROP_WORDS = {"european", "eurasian", "common", "western", "northern", "eastern"}

BLACK, WHITE = (0, 0, 0), (255, 255, 255)

_has_buttons = False        # set by run() once the buttons are found


def bird_names(com_name, sci_name=None):
    """(name to show, words to search poems for), from photos_info/birdinfo.json.
    Other birds lose words like "European" and are searched by their last word."""
    entry = bird_info(com_name, sci_name)
    words = [w for w in com_name.split() if w.lower() not in DROP_WORDS] or com_name.split()
    return entry.get("short_name") or " ".join(words), entry.get("search") or [words[-1].lower()]


# --- Drawing ---

def hints(page):
    """[(letter, label)] for the buttons that work on this page."""
    if not _has_buttons:
        return []
    return [(buttons.letter(job), label) for job, label in HINTS[page]
            if buttons.letter(job) and (job != "song" or birdsong.has_speaker())]


def draw_hints(d, hint_list, x, y, k):
    """Button hints, e.g. [A] browse  [D] birdsong, starting at (x, y); k = text size scale."""
    box, gap = int(15 * k), int(12 * k)
    key_font, label_font = screen.font(HINT_KEY_FONT, int(11 * k)), screen.font(HINT_FONT, int(13 * k))
    for key, label in hint_list:
        d.rounded_rectangle((x, y, x + box, y + box), radius=3, fill=BLACK)
        d.text((x + (box - d.textlength(key, font=key_font)) / 2, y + 1), key, font=key_font, fill=WHITE)
        x += box + 4
        d.text((x, y), label, font=label_font, fill=BLACK)
        x += d.textlength(label, font=label_font) + gap


def layout_verse(d, verse_lines, size, width):
    """Wrap the verse; a long line carries on indented. Returns [(text, indent)]."""
    fnt = screen.font(VERSE_FONT, size)
    out = []
    for line in verse_lines:
        parts = screen.wrap(d, line.strip(), fnt, width - size) or [""]
        out.append((parts[0], 0))
        out += [(p, size) for p in parts[1:]]
    return out


def render(size, name, photo, credit, verse, footer=None, hint_list=()):
    """The screen picture; size = (width, height) in portrait.
    footer = (left text, right text, right colour) along the bottom, or None.
    hint_list = [(letter, label)] button hints above the footer."""
    w, h = size
    k = w / 400                     # text size scale for the screen size
    m = MARGIN
    img = Image.new("RGB", size, WHITE)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    # Name at the top, smaller if it's long
    for name_size in range(int(40 * k), int(22 * k), -2):
        f = screen.font(NAME_FONT, name_size)
        if d.textlength(name, font=f) <= w - 2 * m:
            break
    d.text((m, m - name_size // 6), screen.shorten(d, name, f, w - 2 * m), font=f, fill=BLACK)
    y = m + name_size + 10          # y = how far down the screen

    # Photo across the full width (a tall photo is trimmed top and bottom)
    if photo:
        try:
            pic = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
            photo_h = min(round(w * pic.height / pic.width), int(h * PHOTO_MAX_SHARE))
            img.paste(ImageOps.fit(pic, (w, photo_h)), (0, y))
            y += photo_h
        except Exception as e:
            print(f"Couldn't use photo {photo}: {e}")

    # Photo credit, small, just under the photo on the right
    if credit:
        f = screen.font(SMALL_FONT, 10)
        credit = screen.shorten(d, credit, f, w - 2 * m)
        d.text((w - m - d.textlength(credit, font=f), y + 2), credit, font=f, fill=BLACK)
        y += 14

    # Footer: IP address left, update time (or "Sleeping since") right;
    # on browse pages, the place in the list left and when last heard right
    bottom = h - m                  # bottom of the space for the verse
    if footer:
        left, right, colour = footer
        f = screen.font(VERSE_FONT, int(12 * k))
        footer_y = h - m - int(12 * k)
        d.text((m, footer_y), left, font=f, fill=BLACK)
        d.text((w - m - d.textlength(right, font=f), footer_y), right, font=f, fill=colour)
        bottom = footer_y - 8

    # Button hints above the footer
    if hint_list:
        bottom -= int(15 * k)
        draw_hints(d, hint_list, m, bottom, k)
        bottom -= 8

    if not verse:
        return img

    # Verse: the largest size that fits, without wrapping lines if possible; author and title below
    y += 12
    text_w = w - 2 * m
    f_source = screen.font(SMALL_FONT, int(13 * k))
    source_h = int(17 * k)
    source = "— " + ", ".join(x for x in (verse["author"], verse["title"]) if x)
    source = screen.shorten(d, source, f_source, text_w)
    space = bottom - y - 6 - source_h
    sizes = range(int(24 * k), int(12 * k), -1)
    layouts = {s: layout_verse(d, verse["lines"], s, text_w) for s in sizes}
    fits = [s for s in sizes if len(layouts[s]) * int(s * 1.35) <= space] or [sizes[-1]]
    size = next((s for s in fits if len(layouts[s]) == len(verse["lines"])), fits[0])
    line_h = int(size * 1.35)
    f = screen.font(VERSE_FONT, size)
    for text, indent in layouts[size][:max(space // line_h, 1)]:
        d.text((m + indent, y), text, font=f, fill=BLACK)
        y += line_h
    d.text((w - m - d.textlength(source, font=f_source), y + 6), source, font=f_source, fill=BLACK)
    return img


_shown = None       # (name, photo, credit, verse) on screen, to redraw as the sleeping screen


def show_bird(scr, com_name, sci_name, page="live", footer=None):
    """Draw a bird with a new verse. page = "live" or "browse", for the button hints.
    footer = (left text, right text, colour), or None for the IP address and update time."""
    global _shown
    name, words = bird_names(com_name, sci_name)
    photo, credit = photos.get_photo(com_name, sci_name)
    verse = poems.find_verse(com_name, words)
    print(f"{name}: " + (f'{verse["author"]}, "{verse["title"]}"' if verse else "no verse found"))
    _shown = (name, photo, credit, verse)
    if footer is None and SHOW_FOOTER:
        footer = status.footer()
    width, height = scr.size
    scr.show(render((height, width), *_shown, footer, hints(page)), ROTATE, SATURATION)


def show_page(scr, species, index):
    """Draw the browse page for species[index]: the same as the live screen, with its
    place in the list and when it was last heard along the bottom."""
    sp = species[index]
    heard = datetime.strptime(sp["last_heard"][:16], "%Y-%m-%d %H:%M").strftime(HEARD_TEXT)
    print(f"Browsing {index + 1} of {len(species)}: {sp['Com_Name']} - updating the screen")
    show_bird(scr, sp["Com_Name"], sp["Sci_Name"], "browse", (f"{index + 1} of {len(species)}", heard, BLACK))


def redraw(scr):
    """Redraw the bird on the live screen (same verse) with a new footer."""
    if _shown:
        width, height = scr.size
        scr.show(render((height, width), *_shown, status.footer(), hints("live")), ROTATE, SATURATION)


def show_waiting(scr, sleeping=None):
    """Draw the waiting screen, before BirdNET-Pi has heard any birds.
    sleeping = time: "Sleeping since" along the bottom."""
    if not sleeping:
        print("No birds in the database yet - showing the waiting screen")
    width, height = scr.size
    scr.show(screen.waiting((height, width), status.footer(sleeping)), ROTATE, SATURATION)


def show_sleeping(scr, since):
    """Redraw the bird on screen (same verse), or the waiting screen if no birds yet,
    with "Sleeping since" along the bottom."""
    print("Showing the sleeping screen")
    if not _shown:
        show_waiting(scr, since)
        return
    width, height = scr.size
    scr.show(render((height, width), *_shown, status.footer(since)), ROTATE, SATURATION)


# --- Running ---

def same(a, b):
    """True if two detections are the same one."""
    return b is not None and (a["Date"], a["Time"], a["Com_Name"]) == (b["Date"], b["Time"], b["Com_Name"])


def run(scr):
    """Show each new bird, and answer the buttons, until stopped."""
    # Buttons
    global _has_buttons
    btns = None
    try:
        btns = buttons.Buttons()
        _has_buttons = True
        print("Buttons ready: " + ", ".join(f"{job} = GPIO {pin}" for job, pin in buttons.PINS.items()))
    except Exception as e:
        print(f"Buttons not available, so the live screen only ({e})")

    page = "live"                       # "live" or "browse"
    shown, last_draw = None, 0.0        # shown = the detection on the live screen
    waiting = False                     # True once the waiting screen is shown
    species, index, last_press = [], 0, 0.0

    # Shutdown or reboot: the sleeping screen first
    status.on_shutdown(lambda since: show_sleeping(scr, since))

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
                status.sleep(lambda since: show_sleeping(scr, since))
                if buttons.shutdown():
                    return
                status.wake()
                page, shown, last_draw = "live", None, 0.0
                continue

            # Live button: back to the live screen (drawn below)
            if "live" in presses and page != "live":
                birdsong.stop()
                page, shown, last_draw = "live", None, 0.0

            # Browse button: most recent bird first, then one further back each press
            elif "browse" in presses:
                steps = presses.count("browse")
                birdsong.stop()
                if page != "browse":
                    species, index = birdnet.recent_species(RECENT_SPECIES_LIMIT), 0
                    steps -= 1
                if species:
                    page = "browse"
                    index = (index + steps) % len(species)
                    if "song" in presses:
                        birdsong.toggle(species[index]["Com_Name"])
                    show_page(scr, species, index)
                last_press = time.time()
                continue

            # Song button: the bird on screen
            elif "song" in presses:
                if page == "browse":
                    birdsong.toggle(species[index]["Com_Name"])
                    last_press = time.time()
                elif shown:
                    birdsong.toggle(shown["Com_Name"])
                continue

            # Browsing: back to live after BROWSE_TIMEOUT_SECONDS without a press
            if page == "browse":
                if time.time() - last_press < BROWSE_TIMEOUT_SECONDS:
                    continue
                print("No presses for a while - back to the live screen")
                birdsong.stop()
                page, shown, last_draw = "live", None, 0.0

            # Live: the waiting screen (once) until the first bird
            det = birdnet.latest()
            if det is None:
                if not waiting:
                    show_waiting(scr)
                    waiting = True

            # Live: a new bird, at most every MIN_REFRESH_SECONDS
            elif not same(det, shown) and time.time() - last_draw >= MIN_REFRESH_SECONDS:
                show_bird(scr, det["Com_Name"], det["Sci_Name"])
                shown, last_draw = det, time.time()

            # Live: redraw if the IP address has changed (checked every IP_CHECK_MINUTES)
            elif SHOW_FOOTER and status.ip_changed():
                redraw(scr)
        except Exception:
            log_error()
