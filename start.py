#!/usr/bin/env python3
"""Starts the display chosen in settings.toml.

    .venv/bin/python start.py                        keep running (what the service does)
    .venv/bin/python start.py --once                 show the latest bird, then stop
    .venv/bin/python start.py --bird "European Robin"   show one bird, then stop
    .venv/bin/python start.py --page browse          full display: show browse, chart or sleep
    .venv/bin/python start.py --test-buttons         print each button pressed

Add --preview test.png to save a picture instead of using the screen, with
--size 800x480 to try another screen size and --display to try the other display.
"""

import argparse
import importlib
import os
import sys
import tomllib
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(ROOT, "settings.toml")

# The file each section of settings.toml changes settings in
SECTIONS = {
    "full": "full.display",
    "browse": "full.browse",
    "chart": "full.chart",
    "simple": "simple.display",
    "poems": "simple.poems",
    "buttons": "common.buttons",
    "sound": "common.birdsong",
    "birdnet": "common.birdnet",
}
TOP_LEVEL = {"display", "nightly_update", "debug"}

# What  debug = true  in settings.toml changes, to update the screen as fast as possible
DEBUG_SETTINGS = {
    "full.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "simple.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "common.buttons": {"EXTRA_PRESS_WAIT": 0.1},
    "common.screen": {"DEBUG": True},       # draw in the background, don't wait for the screen
}


class Timestamped:
    """Starts every line printed with the date and time, for the log."""

    def __init__(self, stream):
        self.stream, self.new_line = stream, True

    def write(self, text):
        for piece in text.splitlines(keepends=True):
            if self.new_line:
                self.stream.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S  "))
            self.stream.write(piece)
            self.new_line = piece.endswith("\n")
        self.stream.flush()

    def flush(self):
        self.stream.flush()


def load_settings():
    """settings.toml as a dict, applied to the files named in SECTIONS."""
    if not os.path.exists(SETTINGS):
        sys.exit("settings.toml is missing - run: bash install.sh")
    try:
        with open(SETTINGS, "rb") as f:
            settings = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"Mistake in settings.toml: {e}")

    for section, values in settings.items():
        if section in TOP_LEVEL:
            continue
        if section not in SECTIONS or not isinstance(values, dict):
            print(f"settings.toml: [{section}] isn't a section I know - ignored")
            continue
        module = importlib.import_module(SECTIONS[section])
        for key, value in values.items():
            name = key.upper()
            if not hasattr(module, name):
                print(f"settings.toml: '{key}' isn't a setting in [{section}] - ignored")
            elif isinstance(getattr(module, name), tuple):
                setattr(module, name, tuple(value))
            elif isinstance(getattr(module, name), set):
                setattr(module, name, set(value))
            else:
                setattr(module, name, value)

    if settings.get("debug"):
        print("Debug mode: checking every second, redrawing at once, not waiting for the screen")
        for path, values in DEBUG_SETTINGS.items():
            for name, value in values.items():
                setattr(importlib.import_module(path), name, value)
    return settings


def main():
    p = argparse.ArgumentParser(description="BirdNET-Pi bird display for the Inky Impression")
    p.add_argument("--once", action="store_true", help="show the latest bird, then stop")
    p.add_argument("--bird", metavar="NAME", help='show this bird, e.g. "European Robin", then stop')
    p.add_argument("--page", choices=["browse", "chart", "sleep"], help="full display: show this page, then stop")
    p.add_argument("--preview", metavar="FILE.png", help="save a picture instead of using the screen")
    p.add_argument("--size", metavar="WxH", help="screen size for --preview, e.g. 800x480")
    p.add_argument("--display", choices=["full", "simple"], help="use this display, not the one in settings.toml")
    p.add_argument("--test-buttons", action="store_true", help="print each button pressed")
    args = p.parse_args()

    sys.stdout = Timestamped(sys.stdout)
    sys.stderr = Timestamped(sys.stderr)

    settings = load_settings()
    name = args.display or settings.get("display", "full")
    if name not in ("full", "simple"):
        sys.exit(f'settings.toml: display = "{name}" - it should be "full" or "simple"')
    size = tuple(int(n) for n in args.size.lower().split("x")) if args.size else None

    if args.test_buttons:
        return test_buttons()

    from common.screen import Screen
    display = importlib.import_module(name + ".display")
    if not (args.once or args.bird or args.page or args.preview):
        print(f"===== Starting the {name} display =====")
    scr = Screen(args.preview, size)
    try:
        display.run(scr, args)
        scr.finish()
    except KeyboardInterrupt:
        print("Stopped.")


def test_buttons():
    from common import buttons
    try:
        b = buttons.Buttons()
    except Exception as e:
        sys.exit(f"Buttons not available ({e}). Is the display running? sudo systemctl stop bbbb-display")
    print("Press a button (Ctrl+C to stop). Pins: "
          + ", ".join(f"{job} = GPIO {pin}" for job, pin in buttons.PINS.items()))
    try:
        while True:
            for job in b.wait(1):
                print(f"{job} (GPIO {buttons.PINS[job]})")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
