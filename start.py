#!/usr/bin/env python3
"""Starts the display chosen in settings.toml (run by the bbbb-display service)."""

import importlib
import os
import sys
import tomllib
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(ROOT, "settings.toml")

# settings.toml sections
SECTIONS = {
    "full": "full.display",
    "simple": "simple.display",
}
TOP_LEVEL = {"display", "nightly_update", "debug"}

# debug  mode settings
DEBUG_SETTINGS = {
    "full.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "simple.display": {"POLL_SECONDS": 1, "MIN_REFRESH_SECONDS": 0},
    "common.buttons": {"EXTRA_PRESS_WAIT": 0.1},
    "common.status": {"IP_CHECK_MINUTES": 0.5},
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


def main():
    sys.stdout = Timestamped(sys.stdout)
    sys.stderr = Timestamped(sys.stderr)

    settings = load_settings()
    name = settings.get("display", "full")
    if name not in ("full", "simple"):
        sys.exit(f'settings.toml: display = "{name}" - it should be "full" or "simple"')

    # Run the display
    from common.screen import Screen
    display = importlib.import_module(name + ".display")
    print(f"===== Starting the {name} display =====")
    try:
        display.run(Screen())
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
