"""The e-ink screen, fonts and text wrapping."""

import socket

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
WAITING_TEXT = "Waiting for the first bird"


class Screen:
    """The Inky screen. size is in landscape, e.g. (600, 400)."""

    def __init__(self):
        from inky.auto import auto
        self.inky = auto(ask_user=False, verbose=True)
        self.size = tuple(self.inky.resolution)

    def show(self, img, rotate=0, saturation=0.5):
        """Draw img on the screen (~25 s)."""
        img = img.rotate(rotate, expand=True)
        if img.size != self.size:
            raise ValueError(f"picture is {img.size}, the screen is {self.size} - check rotate")
        self.inky.set_image(img, saturation=saturation)
        self.inky.show()


def waiting(size, footer):
    """The screen before BirdNET-Pi has heard any birds: the Pi's name, WAITING_TEXT,
    and footer = (left text, right text, right colour) along the bottom."""
    w, h = size
    k = min(w, h) / 400             # text size scale for the screen size
    m = 16
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"

    # Pi's name at the top
    f = font("DejaVuSans-Bold.ttf", int(30 * k))
    d.text((m, m), shorten(d, socket.gethostname(), f, w - 2 * m), font=f, fill=(0, 0, 0))

    # Message in the middle
    f = font("DejaVuSans-Bold.ttf", int(26 * k))
    lines = wrap(d, WAITING_TEXT, f, w - 2 * m)
    y = (h - len(lines) * int(36 * k)) // 2
    for line in lines:
        d.text((m, y), line, font=f, fill=(0, 0, 0))
        y += int(36 * k)

    # Footer: IP address left, update time right
    left, right, colour = footer
    f = font("DejaVuSans-Bold.ttf", int(14 * k))
    y = h - m - int(14 * k)
    d.text((m, y), left, font=f, fill=(0, 0, 0))
    d.text((w - m - d.textlength(right, font=f), y), right, font=f, fill=colour)
    return img


def font(name, size):
    """A DejaVu font at this size."""
    return ImageFont.truetype(FONT_DIR + name, size)


def wrap(draw, text, fnt, width):
    """Text split into lines no wider than width."""
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
    """Text cut with "…" to fit width."""
    if draw.textlength(text, font=fnt) <= width:
        return text
    while len(text) > 1 and draw.textlength(text + "…", font=fnt) > width:
        text = text[:-1]
    return text.rstrip(" ,;:") + "…"
