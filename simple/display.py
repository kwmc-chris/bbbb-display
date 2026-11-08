"""The simple display, in portrait: the latest bird's everyday name (Robin, not
European Robin), its photo across the width, and a verse from a classic poem
that mentions it - a different verse each time.

Buttons: "song" plays or stops the bird's song; hold the SHUTDOWN buttons to shut down.
"""

import time

from PIL import Image, ImageDraw, ImageOps

from common import bird_info, birdnet, birdsong, buttons, log_error, photos, screen
from simple import poems

# --- Settings (change any of these under [simple] in settings.toml) ---
ROTATE = 90                 # 90 or 270, depending which way up the screen is
SATURATION = 0.5            # photo colour strength, 0-1
POLL_SECONDS = 30           # how often to check for a new bird
MIN_REFRESH_SECONDS = 180   # shortest gap between redraws
AUTOPLAY_SONG = False       # play each new bird's song
PHOTO_MAX_SHARE = 0.6       # most of the screen height a tall photo may take
MARGIN = 16
NAME_FONT = "DejaVuSans-Bold.ttf"
VERSE_FONT = "DejaVuSans-Bold.ttf"
SMALL_FONT = "DejaVuSans.ttf"
DROP_WORDS = {"european", "eurasian", "common", "western", "northern", "eastern"}

BLACK, WHITE = (0, 0, 0), (255, 255, 255)


def bird_names(com_name, sci_name=None):
    """(name to show, words to search poems for), from common/birdinfo.json.
    Other birds lose words like "European" and are searched by their last word."""
    entry = bird_info(com_name, sci_name)
    words = [w for w in com_name.split() if w.lower() not in DROP_WORDS] or com_name.split()
    return entry.get("short_name") or " ".join(words), entry.get("search") or [words[-1].lower()]


# --- Drawing ---

def layout_verse(d, verse_lines, size, width):
    """Wrap the verse; a long line carries on indented. Returns [(text, indent)]."""
    fnt = screen.font(VERSE_FONT, size)
    out = []
    for line in verse_lines:
        parts = screen.wrap(d, line.strip(), fnt, width - size) or [""]
        out.append((parts[0], 0))
        out += [(p, size) for p in parts[1:]]
    return out


def render(size, name, photo, credit, verse):
    """The screen picture; size = (width, height) in portrait."""
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

    if not verse:
        return img

    # Verse: the largest size that fits, without wrapping lines if possible; author and title below
    y += 12
    text_w = w - 2 * m
    f_source = screen.font(SMALL_FONT, int(13 * k))
    source_h = int(17 * k)
    source = "— " + ", ".join(x for x in (verse["author"], verse["title"]) if x)
    source = screen.shorten(d, source, f_source, text_w)
    space = h - y - m - 6 - source_h
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


def show_bird(scr, com_name, sci_name):
    name, words = bird_names(com_name, sci_name)
    photo, credit = photos.get_photo(com_name, sci_name, name)
    verse = poems.find_verse(com_name, words)
    print(f"{name}: " + (f'{verse["author"]}, "{verse["title"]}"' if verse else "no verse found"))
    width, height = scr.size
    scr.show(render((height, width), name, photo, credit, verse), ROTATE, SATURATION)


# --- Running ---

def same(a, b):
    """True if two detections are the same one."""
    return b is not None and (a["Date"], a["Time"], a["Com_Name"]) == (b["Date"], b["Time"], b["Com_Name"])


def run(scr, args):
    """args from start.py: once, bird, page, preview."""
    # One picture, then stop
    if args.page:
        print("--page is only for the full display")
        return
    if args.bird:
        return show_bird(scr, args.bird, birdnet.sci_name(args.bird))

    # Buttons
    btns = None
    if buttons.ENABLED and not (args.once or args.preview):
        try:
            btns = buttons.Buttons()
            print("Buttons ready: " + ", ".join(f"{job} = GPIO {pin}" for job, pin in buttons.PINS.items()
                                                if job == "song" or job in buttons.SHUTDOWN))
        except Exception as e:
            print(f"Buttons not available ({e})")

    if not (args.once or args.preview):
        print("Watching for new birds")
    shown, last_draw = None, 0.0        # shown = the detection on screen
    while True:
        # New bird: show it (at most every MIN_REFRESH_SECONDS)
        try:
            det = birdnet.latest()
            if det and not same(det, shown) and time.time() - last_draw >= MIN_REFRESH_SECONDS:
                if AUTOPLAY_SONG:
                    birdsong.play(det["Com_Name"])
                show_bird(scr, det["Com_Name"], det["Sci_Name"])
                shown, last_draw = det, time.time()
            elif det is None and (args.once or args.preview):
                print("No birds in the database yet.")
        except Exception:
            log_error()
        if args.once or args.preview:
            return

        # Wait for a button press or POLL_SECONDS
        presses = btns.wait(POLL_SECONDS) if btns else (time.sleep(POLL_SECONDS) or [])
        try:
            if btns and btns.shutdown_held(presses):
                birdsong.stop()
                print("Shutdown buttons held - shutting down")
                if buttons.shutdown():
                    return
            elif "song" in presses and shown:
                birdsong.toggle(shown["Com_Name"])
        except Exception:
            log_error()
