"""The e-ink screen, fonts and text wrapping."""

import threading
import time

from PIL import ImageFont

from common import log_error

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
PREVIEW_SIZE = (600, 400)       # screen size used for --preview (unless --size is given)
DEBUG = False                   # set by  debug = true  in settings.toml (see below)

_missing_fonts = set()


class Screen:
    """The Inky screen, or a picture file with --preview.
    size is the screen in landscape, e.g. (600, 400) or (800, 480).

    Normally show() waits until the screen has finished (~25 s). In debug mode
    it returns at once and the picture is drawn in the background without
    waiting for the screen, so a new picture can start before the last one has
    finished. If several arrive while it's busy, only the newest is drawn."""

    def __init__(self, preview=None, size=None):
        self.preview = preview
        self._next = None               # debug mode: the picture waiting to be drawn
        self._worker = None
        self._lock = threading.Lock()
        if preview:
            self.inky = None
            self.size = size or PREVIEW_SIZE
        else:
            from inky.auto import auto
            self.inky = auto(ask_user=False, verbose=True)
            self.size = tuple(self.inky.resolution)

    def show(self, img, rotate=0, saturation=0.5):
        """Draw img on the screen, or save it with --preview."""
        if self.preview:
            img.save(self.preview)
            print(f"Saved {self.preview}")
            return
        img = img.rotate(rotate, expand=True)     # e.g. portrait -> the screen's landscape
        if img.size != self.size:
            raise ValueError(f"picture is {img.size}, the screen is {self.size} - check rotate")
        if not DEBUG:
            return self._draw(img, saturation)
        with self._lock:
            self._next = (img, saturation)
            if self._worker is None:
                self._worker = threading.Thread(target=self._draw_newest, daemon=True)
                self._worker.start()

    def finish(self):
        """Wait for a background drawing to finish (debug mode)."""
        worker = self._worker
        if worker:
            worker.join()

    def _draw_newest(self):
        while True:
            with self._lock:
                job, self._next = self._next, None
                if job is None:
                    self._worker = None
                    return
            start = time.time()
            try:
                self._draw(*job, wait=False)
                print(f"Screen sent in {time.time() - start:.1f} s")
            except Exception:
                log_error()

    def _draw(self, img, saturation, wait=True):
        try:
            self.inky.set_image(img, saturation=saturation)
        except TypeError:                         # screens without a saturation option
            self.inky.set_image(img)
        try:
            self.inky.show(busy_wait=wait)        # False: don't wait for the screen to finish
        except TypeError:
            self.inky.show()


def font(name, size):
    """A DejaVu font; if that one's missing, plain DejaVu Sans, else Pillow's own."""
    for f in (name, "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(FONT_DIR + f, size)
        except OSError:
            if f == name and name not in _missing_fonts:
                _missing_fonts.add(name)
                print(f"Font {name} not found, using another (install.sh installs the fonts)")
    try:
        return ImageFont.load_default(size=size)      # Pillow 10.1 and later
    except TypeError:
        return ImageFont.load_default()               # older Pillow: one small size


def wrap(draw, text, fnt, width):
    """Split text into lines no wider than width."""
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if line and draw.textlength(test, font=fnt) > width:
            lines.append(line)
            line = word
        else:
            line = test
    return lines + [line] if line else lines


def shorten(draw, text, fnt, width):
    """Cut text with "…" so it fits width."""
    if draw.textlength(text, font=fnt) <= width:
        return text
    while len(text) > 1 and draw.textlength(text + "…", font=fnt) > width:
        text = text[:-1]
    return text.rstrip(" ,;:") + "…"
