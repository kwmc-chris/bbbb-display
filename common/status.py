"""The footer along the bottom of both displays, and the sleeping screen.
    footer()                    ("IP 192.168.1.20", "Updated Mon 18:22", green)
    ip_changed()                every IP_CHECK_MINUTES: True if the IP address isn't the one on screen
    footer(sleeping=time)       ("", "Sleeping since Mon 18:30", red)
    on_shutdown(draw)           when the Pi shuts down or reboots, run draw(time) first
    sleep(draw)                 run draw(time) now (only once), e.g. for the shutdown buttons
    wake()                      the shutdown didn't happen: allow the sleeping screen again
"""

import signal
import subprocess
import sys
import time
from datetime import datetime

from common import log_error, web

# settings
UPDATED_TEXT = "Updated %a %H:%M"           # %a = day (Mon), %H:%M = time
SLEEP_TEXT = "Sleeping since %a %H:%M"
IP_CHECK_MINUTES = 10                       # how often to check the IP address hasn't changed

GREEN, RED = (0, 255, 0), (255, 0, 0)

_asleep = False                             # True once the sleeping screen is shown
_shown_ip = None                            # the IP text on screen ("IP ..." or "No network")
_last_check = 0.0                           # when ip_changed() last looked


def footer(sleeping=None):
    """(left text, right text, right colour) for the bottom of the screen."""
    global _shown_ip, _last_check
    if sleeping:
        return "", sleeping.strftime(SLEEP_TEXT), RED
    _shown_ip, _last_check = ip_text(), time.time()
    return _shown_ip, datetime.now().strftime(UPDATED_TEXT), GREEN


def ip_text():
    """The IP address as shown, e.g. "IP 192.168.1.20", or "No network"."""
    ip = web.ip_address()
    return f"IP {ip}" if ip else "No network"


def ip_changed():
    """Every IP_CHECK_MINUTES: True if the IP address has changed since the screen was drawn
    (e.g. the network dropped). Otherwise False, without checking."""
    global _last_check
    if _shown_ip is None or time.time() - _last_check < IP_CHECK_MINUTES * 60:
        return False
    _last_check = time.time()
    now = ip_text()
    if now == _shown_ip:
        return False
    print(f"Network changed ({_shown_ip} -> {now}) - updating the screen")
    return True


def sleep(draw):
    """Show the sleeping screen with draw(time), unless it's already showing."""
    global _asleep
    if _asleep:
        return
    _asleep = True
    try:
        draw(datetime.now())
    except Exception:
        log_error()


def wake():
    """The Pi didn't shut down after all, so the sleeping screen can show again later."""
    global _asleep
    _asleep = False


def shutting_down():
    """True if the whole Pi is shutting down or rebooting (not just the display restarting)."""
    result = subprocess.run(["systemctl", "is-system-running"], capture_output=True, text=True)
    return result.stdout.strip() == "stopping"


def on_shutdown(draw):
    """When systemd stops the display, show the sleeping screen first if the Pi is
    shutting down or rebooting. A restart (e.g. the nightly update) just stops."""
    def stop(signum, frame):
        if shutting_down():
            print("The Pi is shutting down - showing the sleeping screen")
            sleep(draw)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
