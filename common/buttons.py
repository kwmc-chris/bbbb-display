"""Buttons on GPIO pins: the Inky's own A-D buttons, or your own wired to other pins.

Each job has a GPIO (BCM) pin number in PINS; change them for each Pi under
[buttons] in settings.toml. A button connects its pin to ground (GND).

    buttons = Buttons()
    buttons.wait(30)        jobs pressed, e.g. ["song"], or [] after 30 seconds
    buttons.shutdown_held(presses)   True if the SHUTDOWN buttons are held down
"""

import subprocess
import time

ENABLED = True
PINS = {"browse": 5, "live": 6, "chart": 16, "song": 24}    # job: pin
SHUTDOWN = ["browse", "song"]   # hold these together to shut the Pi down safely
SHUTDOWN_SECONDS = 3

# The Inky Impression's own buttons, so the screen can show "A", "B"... beside each job
INKY_LETTERS = {5: "A", 6: "B", 16: "C", 25: "C", 24: "D"}

DEBOUNCE_SECONDS = 0.3          # ignore a button bouncing within this time
EXTRA_PRESS_WAIT = 0.6          # after a press, wait this long to catch quick extra presses


def letter(job):
    """The Inky button letter for a job ("A"-"D"), or None if it's not on one."""
    return INKY_LETTERS.get(PINS.get(job)) if ENABLED else None


def shutdown():
    """Shut the Pi down. False if it was refused (the user needs sudo without a password)."""
    result = subprocess.run(["sudo", "-n", "shutdown", "-h", "now"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Shutdown failed: {result.stderr.strip() or result.returncode}")
    return result.returncode == 0


class Buttons:
    def __init__(self):
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge, Value

        self._pressed_value = Value.INACTIVE       # pin pulled to ground = pressed
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.FALLING)
        chip = gpiodevice.find_chip_by_platform()
        self._jobs = {chip.line_offset_from_id(pin): job for job, pin in PINS.items()}
        self._lines = chip.request_lines(consumer="bbbb-display",
                                         config=dict.fromkeys(self._jobs, settings))
        self._last_press = {}

    def wait(self, timeout):
        """Jobs pressed within timeout seconds (including presses made while
        the screen was busy redrawing), or [] if none."""
        if not self._lines.wait_edge_events(timeout):
            return []
        time.sleep(EXTRA_PRESS_WAIT)
        presses = []
        for event in self._lines.read_edge_events():
            job = self._jobs.get(event.line_offset)
            pressed_at = event.timestamp_ns / 1e9      # when it was pressed, not when read
            if job and pressed_at - self._last_press.get(job, 0) >= DEBOUNCE_SECONDS:
                self._last_press[job] = pressed_at
                presses.append(job)
        return presses

    def down(self):
        """Jobs whose buttons are held down right now."""
        values = self._lines.get_values()
        return {self._jobs[o] for o, v in zip(self._lines.offsets, values)
                if v == self._pressed_value}

    def shutdown_held(self, presses):
        """True if a SHUTDOWN button was just pressed and all of them are now
        held together for SHUTDOWN_SECONDS. A normal press returns False at once."""
        wanted = set(SHUTDOWN)
        if not wanted or not wanted & set(presses) or not wanted <= set(PINS):
            return False
        start = time.monotonic()
        while not wanted <= self.down():           # allow a moment to press the other one
            if not wanted & self.down() or time.monotonic() - start > 1:
                return False
            time.sleep(0.05)
        start = time.monotonic()
        while time.monotonic() - start < SHUTDOWN_SECONDS - EXTRA_PRESS_WAIT:
            if not wanted <= self.down():
                return False
            time.sleep(0.05)
        return True

    def clear(self):
        """Forget presses made while the screen was redrawing."""
        while self._lines.wait_edge_events(0):
            self._lines.read_edge_events()
