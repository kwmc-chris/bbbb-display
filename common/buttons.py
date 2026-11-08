"""Buttons on GPIO pins: the Inky's own A-D buttons, or your own on other pins.
A button connects its pin to ground (GND). Pins are set under [buttons] in settings.toml.

    b = Buttons()
    b.wait(30)                 jobs pressed, e.g. ["song"], or [] after 30 seconds
    b.shutdown_held(presses)   True if the SHUTDOWN buttons are held down
"""

import subprocess
import time

# --- Settings (change any of these under [buttons] in settings.toml) ---
ENABLED = True
PINS = {"browse": 5, "live": 6, "song": 24}     # job: GPIO pin
SHUTDOWN = ["browse", "song"]   # hold these together to shut down
SHUTDOWN_SECONDS = 3
INKY_LETTERS = {5: "A", 6: "B", 16: "C", 25: "C", 24: "D"}    # the Inky's buttons
DEBOUNCE_SECONDS = 0.3          # ignore repeats of one button within this time
EXTRA_PRESS_WAIT = 0.6          # after a press, wait this long for more presses


def letter(job):
    """The Inky button letter for a job ("A"-"D"), or None."""
    return INKY_LETTERS.get(PINS.get(job)) if ENABLED else None


def shutdown():
    """Shut the Pi down. False if it was refused."""
    result = subprocess.run(["sudo", "-n", "shutdown", "-h", "now"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Shutdown failed: {result.stderr.strip() or result.returncode}")
    return result.returncode == 0


class Buttons:
    def __init__(self):
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge, Value

        self._pressed_value = Value.INACTIVE       # pin at ground = pressed
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.FALLING)
        chip = gpiodevice.find_chip_by_platform()
        self._jobs = {chip.line_offset_from_id(pin): job for job, pin in PINS.items()}
        self._lines = chip.request_lines(consumer="bbbb-display",
                                         config=dict.fromkeys(self._jobs, settings))
        self._last_press = {}

    def wait(self, timeout):
        """Jobs pressed within timeout seconds, including any pressed during a redraw."""
        if not self._lines.wait_edge_events(timeout):
            return []
        time.sleep(EXTRA_PRESS_WAIT)
        presses = []
        for event in self._lines.read_edge_events():
            job = self._jobs.get(event.line_offset)
            pressed_at = event.timestamp_ns / 1e9      # time of the press itself
            if job and pressed_at - self._last_press.get(job, 0) >= DEBOUNCE_SECONDS:
                self._last_press[job] = pressed_at
                presses.append(job)
        return presses

    def down(self):
        """Jobs whose buttons are held down now."""
        values = self._lines.get_values()
        return {self._jobs[o] for o, v in zip(self._lines.offsets, values)
                if v == self._pressed_value}

    def shutdown_held(self, presses):
        """True if a SHUTDOWN button was pressed and all of them are held for SHUTDOWN_SECONDS."""
        wanted = set(SHUTDOWN)
        if not wanted or not wanted & set(presses) or not wanted <= set(PINS):
            return False
        # Up to 1 second for the other button to go down
        start = time.monotonic()
        while not wanted <= self.down():
            if not wanted & self.down() or time.monotonic() - start > 1:
                return False
            time.sleep(0.05)
        # Then held together
        start = time.monotonic()
        while time.monotonic() - start < SHUTDOWN_SECONDS - EXTRA_PRESS_WAIT:
            if not wanted <= self.down():
                return False
            time.sleep(0.05)
        return True

    def clear(self):
        """Forget presses made during a redraw."""
        while self._lines.wait_edge_events(0):
            self._lines.read_edge_events()
