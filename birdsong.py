#!/usr/bin/env python3
"""
birdsong.py - plays BirdNET-Pi's recordings for bbbb-display.py (button D).

    find_recording(db, name)   path of a saved recording of that species, or None
    toggle(db, name)           play it, or stop if already playing
    choose_output()            (ALSA device, description): USB speaker if
                               plugged in, otherwise the headphone socket

Output is chosen at every press, so a USB speaker plugged in later is used.
The Pi's default sound device is NOT changed - BirdNET-Pi records through it.

BirdNET-Pi saves a short clip of each detection in
~/BirdSongs/Extracted/By_Date/<date>/<Common_Name>/ and deletes old ones over
time, so only recordings still on disk can be played.

Needs an audio player: ffplay (comes with ffmpeg) or: sudo apt install mpg123

Test:  python3 birdsong.py "European Robin"     find and play a recording
       python3 birdsong.py --output             which speaker would be used
       python3 birdsong.py --players            audio players found
"""

# =============================================================================
# SETTINGS
# =============================================================================

import os

DATABASE = os.path.expanduser("~/BirdNET-Pi/scripts/birds.db")
CONF_PATHS = ["/etc/birdnet/birdnet.conf", os.path.expanduser("~/BirdNET-Pi/birdnet.conf")]
DEFAULT_EXTRACTED = os.path.expanduser("~/BirdSongs/Extracted")   # if not in BirdNET-Pi's settings

RECORDING_CHOICE = "best"     # "best" = highest confidence, "latest" = most recent
RECORDINGS_CHECKED = 50       # recent detections of the species to consider

# "auto" = USB speaker if plugged in, else headphone socket.
# Or an ALSA device to always use, e.g. "plughw:CARD=Headphones,DEV=0"
AUDIO_OUTPUT = "auto"
HEADPHONE_CARD = "Headphones"   # the Pi 4's 3.5 mm socket
ASOUND_DIR = "/proc/asound"     # where Linux lists sound cards

PLAYERS = ["ffplay", "mpg123", "play", "mpv", "cvlc"]   # tried in this order

# =============================================================================

import glob
import re
import shutil
import sqlite3
import subprocess

_process = None               # the player currently running

# --- Recordings --------------------------------------------------------------

def birdnet_config():
    """BirdNET-Pi's settings file as a dict."""
    conf = {}
    for path in CONF_PATHS:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        conf[key.strip()] = value.strip().strip('"').strip("'")
            break
        except OSError:
            continue
    return conf


def extracted_dir():
    """Where BirdNET-Pi keeps its recordings (expands ${RECS_DIR}, $HOME, ~)."""
    conf = birdnet_config()
    value = conf.get("EXTRACTED", "")
    if not value:
        return DEFAULT_EXTRACTED
    names = dict(conf, HOME=os.path.expanduser("~"))
    for _ in range(3):        # settings can refer to other settings
        value = re.sub(r"\$\{?(\w+)\}?", lambda m: names.get(m.group(1), m.group(0)), value)
    return os.path.expanduser(value)


def find_recording(db_path, com_name):
    """A recording of the species still on disk (see RECORDING_CHOICE), or None."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute(
            "SELECT Date, File_Name, Confidence FROM detections WHERE Com_Name = ? "
            "ORDER BY Date DESC, Time DESC LIMIT ?", (com_name, RECORDINGS_CHECKED)).fetchall()
    finally:
        con.close()
    if RECORDING_CHOICE == "best":
        rows = sorted(rows, key=lambda r: -float(r[2] or 0))

    base = os.path.join(extracted_dir(), "By_Date")
    folder = com_name.replace("'", "").replace(" ", "_")     # as BirdNET-Pi names it
    for date, file_name, _ in rows:
        if not file_name:
            continue
        path = os.path.join(base, date, folder, file_name)
        if os.path.isfile(path):
            return path
        matches = glob.glob(os.path.join(base, date, "*", file_name))   # other folder naming
        if matches:
            return matches[0]
    return None

# --- Choosing the speaker ----------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def sound_cards():
    """[{id, name, usb, playback_devices}] for each sound card."""
    cards = []
    descriptions = {}
    for line in _read(os.path.join(ASOUND_DIR, "cards")).splitlines():
        m = re.match(r"\s*(\d+)\s+\[.*?\]:\s*.*? - (.*)", line)
        if m:
            descriptions[m.group(1)] = m.group(2).strip()
    for card_dir in sorted(glob.glob(os.path.join(ASOUND_DIR, "card[0-9]*"))):
        number = os.path.basename(card_dir)[4:]
        playback = sorted(int(os.path.basename(p)[3:-1])          # pcm0p -> 0
                          for p in glob.glob(os.path.join(card_dir, "pcm*p")))
        cards.append({
            "id": _read(os.path.join(card_dir, "id")) or number,
            "name": descriptions.get(number, ""),
            "usb": os.path.exists(os.path.join(card_dir, "usbid")),
            "playback_devices": playback,
        })
    return cards


def choose_output():
    """(ALSA device, description). USB card that can play sound (so a USB
    microphone is skipped), else the headphone socket, else the default."""
    if AUDIO_OUTPUT != "auto":
        return AUDIO_OUTPUT, "set in AUDIO_OUTPUT"
    cards = sound_cards()
    for card in cards:
        if card["usb"] and card["playback_devices"]:
            device = f"plughw:CARD={card['id']},DEV={card['playback_devices'][0]}"
            return device, f"USB speaker ({card['name'] or card['id']})"
    for card in cards:
        if card["id"] == HEADPHONE_CARD and card["playback_devices"]:
            return f"plughw:CARD={HEADPHONE_CARD},DEV={card['playback_devices'][0]}", \
                "3.5 mm headphone socket"
    return "default", "default sound device"


def _command(player, device, path):
    """Command and extra environment for a player, sending sound to device."""
    use = device != "default"
    if player == "ffplay":
        env = {"SDL_AUDIODRIVER": "alsa", **({"AUDIODEV": device} if use else {})}
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path], env
    if player == "mpg123":
        return ["mpg123", "-q", "-o", "alsa"] + (["-a", device] if use else []) + [path], {}
    if player == "play":                                     # from sox
        return ["play", "-q", path], {"AUDIODRIVER": "alsa", **({"AUDIODEV": device} if use else {})}
    if player == "mpv":
        return ["mpv", "--no-video", "--really-quiet"] + \
            ([f"--audio-device=alsa/{device}"] if use else []) + [path], {}
    return ["cvlc", "--play-and-exit", "--quiet", "--aout=alsa"] + \
        ([f"--alsa-audio-device={device}"] if use else []) + [path], {}

# --- Playing -----------------------------------------------------------------

def available_players():
    return [p for p in PLAYERS if shutil.which(p)]


def play(path):
    """Start playing path in the background. Returns True if a player started."""
    global _process
    stop()
    players = available_players()
    if not players:
        print("No audio player found - install one with: sudo apt install mpg123")
        return False
    device, description = choose_output()
    cmd, env = _command(players[0], device, path)
    _process = subprocess.Popen(cmd, env=dict(os.environ, **env),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Playing {os.path.basename(path)} through the {description}")
    return True


def is_playing():
    return _process is not None and _process.poll() is None


def stop():
    global _process
    if is_playing():
        _process.terminate()
        try:
            _process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


def toggle(db_path, com_name):
    """Button D: stop if playing, otherwise play a recording of com_name."""
    if is_playing():
        stop()
        print("Birdsong stopped.")
        return
    path = find_recording(db_path, com_name)
    if path:
        play(path)
    else:
        print(f"No recording of {com_name} found on disk.")


if __name__ == "__main__":
    import sys
    if "--players" in sys.argv:
        print("Audio players found:", ", ".join(available_players()) or "none")
    elif "--output" in sys.argv:
        device, description = choose_output()
        print(f"{description}  [{device}]")
    else:
        names = [a for a in sys.argv[1:] if not a.startswith("--")]
        if not names:
            raise SystemExit('Usage: python3 birdsong.py "European Robin"   (or --output, --players)')
        print("Recordings folder:", extracted_dir())
        path = find_recording(DATABASE, names[0])
        if not path:
            raise SystemExit(f"No recording of {names[0]} found.")
        if play(path):
            _process.wait()
