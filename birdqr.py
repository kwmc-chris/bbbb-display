#!/usr/bin/env python3
"""
birdqr.py - QR codes for bbbb-display.py (browse pages link to the bird's
Wikipedia article). Needs the "qrcode" package; update.sh installs it.

    qr_images(text)   the QR code as pictures, one per square size in
                      MODULE_SIZES, largest first ([] if qrcode is missing).
                      The browse page uses the largest that fits.

Turn QR codes on/off with SHOW_QR in bbbb-display.py.

Test:  python3 birdqr.py "https://en.wikipedia.org/?curid=25334006" --preview qr.png
"""

# =============================================================================
# SETTINGS
# =============================================================================

MODULE_SIZES = (3, 2)       # pixels per QR square, largest tried first
ERROR_CORRECTION = "M"      # L, M, Q or H: higher survives damage but makes a bigger code

# =============================================================================

from PIL import Image

_warned = False


def qr_matrix(text):
    """The QR code as rows of True (dark) / False squares, or None."""
    global _warned
    try:
        import qrcode
    except ImportError:
        if not _warned:
            print("qrcode package not installed - no QR codes (update.sh installs it)")
            _warned = True
        return None
    level = getattr(qrcode.constants, "ERROR_CORRECT_" + ERROR_CORRECTION)
    qr = qrcode.QRCode(error_correction=level, border=0)    # page margin acts as border
    qr.add_data(text)
    qr.make(fit=True)
    return qr.get_matrix()


def qr_image(matrix, module_size):
    """Black-on-white picture of a QR matrix, module_size pixels per square."""
    n = len(matrix)
    small = Image.new("1", (n, n), 1)
    small.putdata([0 if dark else 1 for row in matrix for dark in row])
    return small.resize((n * module_size, n * module_size), Image.NEAREST).convert("RGB")


def qr_images(text, sizes=MODULE_SIZES):
    """QR pictures for text, largest first; [] if it can't be made."""
    matrix = qr_matrix(text) if text else None
    return [qr_image(matrix, s) for s in sizes] if matrix else []


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = args[0] if args else "https://en.wikipedia.org/"
    out = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else "qr.png"
    images = qr_images(text)
    if images:
        images[0].save(out)
        print(f"Saved {out} ({images[0].width} px square) for {text}")
