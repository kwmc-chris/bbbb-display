#!/usr/bin/env python3
"""Starts the display chosen in settings.toml.

    .venv/bin/python start.py                        keep running (what the service does)
    .venv/bin/python start.py --once                 show the latest bird, then stop
    .venv/bin/python start.py --bird "European Robin"   show one bird, then stop
    .venv/bin/python start.py --page browse          full display: show browse or sleep, then stop
    .venv/bin/python start.py --test-buttons         print each button pressed
    .venv/bin/python start.py --test-sound           list sound devices, play a beep

Add --preview test.png to save a picture instead of using the screen.
"""

import argparse
import importlib
import os
import sys
import tomllib
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(ROOT, "settings.toml")

# --- settings.toml: each section and the file it changes ---
SECTIONS = {
    "full": "full.display",
    "browse": "full.browse",
    "simple": "simple.display",
    "poems": "simple.poems",
    "buttons": "common.buttons",
    "sound": "common.birdsong",
    "birdnet": "common.birdnet",
}
TOP_LEVEL = {"display", "nightly_update", "debug"}

# What  debug = true  changes
DEBUG_SETTINGS = {
    "full.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "simple.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "common.buttons": {"EXTRA_PRESS_WAIT": 0.1},
}


class Timestamped:
    """Starts every printed line with the date and time."""

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
    """Read settings.toml and apply each section to its file."""
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
            if hasattr(module, key.upper()):
                setattr(module, key.upper(), value)
            else:
                print(f"settings.toml: '{key}' isn't a setting in [{section}] - ignored")

    if settings.get("debug"):
        print("Debug mode: checking every second and redrawing for every new bird")
        for path, values in DEBUG_SETTINGS.items():
            for name, value in values.items():
                setattr(importlib.import_module(path), name, value)
    return settings


def test_buttons():
    """Print each button pressed until Ctrl+C."""
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


def main():
    p = argparse.ArgumentParser(description="BirdNET-Pi bird display for the Inky Impression")
    p.add_argument("--once", action="store_true", help="show the latest bird, then stop")
    p.add_argument("--bird", metavar="NAME", help='show this bird, e.g. "European Robin", then stop')
    p.add_argument("--page", choices=["browse", "sleep"], help="full display: show this page, then stop")
    p.add_argument("--preview", metavar="FILE.png", help="save a picture instead of using the screen")
    p.add_argument("--test-buttons", action="store_true", help="print each button pressed")
    p.add_argument("--test-sound", action="store_true", help="list sound devices and play a beep")
    args = p.parse_args()

    sys.stdout = Timestamped(sys.stdout)
    sys.stderr = Timestamped(sys.stderr)

    settings = load_settings()
    name = settings.get("display", "full")
    if name not in ("full", "simple"):
        sys.exit(f'settings.toml: display = "{name}" - it should be "full" or "simple"')

    if args.test_buttons:
        return test_buttons()
    if args.test_sound:
        from common import birdsong
        return birdsong.test()

    # Run the display
    from common.screen import Screen
    display = importlib.import_module(name + ".display")
    if not (args.once or args.bird or args.page or args.preview):
        print(f"===== Starting the {name} display =====")
    try:
        display.run(Screen(args.preview), args)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
