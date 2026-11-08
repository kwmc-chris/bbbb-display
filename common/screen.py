"""The e-ink screen, fonts and text wrapping."""

from PIL import ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
PREVIEW_SIZE = (600, 400)       # picture size for --preview


class Screen:
    """The Inky screen, or a picture file with --preview. size is in landscape, e.g. (600, 400)."""

    def __init__(self, preview=None):
        self.preview = preview
        if preview:
            self.inky, self.size = None, PREVIEW_SIZE
        else:
            from inky.auto import auto
            self.inky = auto(ask_user=False, verbose=True)
            self.size = tuple(self.inky.resolution)

    def show(self, img, rotate=0, saturation=0.5):
        """Draw img on the screen (~25 s), or save it with --preview."""
        if self.preview:
            img.save(self.preview)
            print(f"Saved {self.preview}")
            return
        img = img.rotate(rotate, expand=True)
        if img.size != self.size:
            raise ValueError(f"picture is {img.size}, the screen is {self.size} - check rotate")
        self.inky.set_image(img, saturation=saturation)
        self.inky.show()


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
