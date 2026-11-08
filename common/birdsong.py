"""Plays BirdNET-Pi's own recording of a bird through the USB speaker.
The recording is levelled with ffmpeg and played with aplay; prepared clips
are kept in cache/songs/.

    toggle(com_name)   play the bird's song, or stop it
    test()             list sound devices and play a beep (start.py --test-sound)
"""

import glob
import os
import re
import subprocess
import time

from common import CACHE, birdnet, web

# --- Settings (change any of these under [sound] in settings.toml) ---
SPEAKER = "auto"        # "auto" (the USB speaker), "none", or an ALSA device name
LOUDNESS = -20          # LUFS: higher (e.g. -16) = louder
HIGHPASS_HZ = 250       # cut sound below this; 0 = off

_player = None          # aplay, while playing


# --- Playing ---

def enabled():
    return SPEAKER != "none"


def toggle(com_name):
    """Stop if playing, otherwise play the bird's song."""
    if is_playing():
        stop()
        print("Birdsong stopped.")
    else:
        play(com_name)


def play(com_name):
    """Play BirdNET-Pi's best recent recording of the bird."""
    stop()
    if not enabled():
        return
    clip = birdnet_clip(com_name)
    if not clip:
        print(f"No BirdNET-Pi recording of {com_name} on disk.")
        return
    wav = os.path.join(CACHE, "songs", web.slug(os.path.splitext(os.path.basename(clip))[0]) + ".wav")
    if os.path.exists(wav) or prepare(clip, wav):
        start_player(wav, com_name)


def start_player(wav, what):
    """Start aplay; log an error if it fails to start."""
    global _player
    device, where = speaker()
    if not device:
        print("No USB speaker found (a USB device with a mic isn't used)")
        return
    _player = subprocess.Popen(["aplay", "-q", "-D", device, wav],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    if _player.poll() not in (None, 0):
        error = _player.stderr.read().strip()
        print(f"Couldn't play {what} through the {where} ({device}): {error or 'no reason given'}")
        _player = None
    else:
        print(f"Playing {what} through the {where}")


def is_playing():
    return _player is not None and _player.poll() is None


def stop():
    global _player
    if is_playing():
        _player.terminate()
        try:
            _player.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _player.kill()
    _player = None


# --- Recordings ---

def birdnet_clip(com_name):
    """BirdNET-Pi's highest-confidence recent clip of the bird still on disk, or None."""
    rows = birdnet.query("SELECT Date, File_Name, Confidence FROM detections WHERE Com_Name = ? "
                         "ORDER BY Date DESC, Time DESC LIMIT 50", com_name)
    # Recordings folder from birdnet.conf, e.g. ${RECS_DIR}/Extracted
    conf = birdnet.config()
    folder = conf.get("EXTRACTED", "") or "~/BirdSongs/Extracted"
    names = dict(conf, HOME=os.path.expanduser("~"))
    for _ in range(3):
        folder = re.sub(r"\$\{?(\w+)\}?", lambda m: names.get(m.group(1), m.group(0)), folder)
    base = os.path.join(os.path.expanduser(folder), "By_Date")
    for row in sorted(rows, key=lambda r: -float(r["Confidence"] or 0)):
        if row["File_Name"]:
            found = glob.glob(os.path.join(base, row["Date"], "*", row["File_Name"]))
            if found:
                return found[0]
    return None


def prepare(clip, wav):
    """Level a clip with ffmpeg into a .wav file; keeps the newest 50."""
    filters = ([f"highpass=f={HIGHPASS_HZ}"] if HIGHPASS_HZ else []) + [
        f"loudnorm=I={LOUDNESS}:TP=-2:LRA=11", "afade=t=in:d=0.05"]
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    old = sorted(glob.glob(os.path.join(os.path.dirname(wav), "*.wav")), key=os.path.getmtime)
    for f in old[:-50]:
        os.remove(f)
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-af", ",".join(filters),
                             "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", wav],
                            capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(wav):
        print(f"Couldn't prepare the recording {clip}: {result.stderr.strip()[:200]}")
        return False
    return True


# --- Speaker ---

def speaker():
    """(ALSA device, description), or (None, None) if there's no USB speaker."""
    if SPEAKER != "auto":
        return SPEAKER, "speaker set in settings.toml"
    for c in sound_cards():
        if c["usb"] and c["playback"] and not c["mic"]:
            return f"plughw:CARD={c['id']},DEV={c['playback'][0]}", f"USB speaker ({c['id']})"
    return None, None


def sound_cards():
    """[{id, usb, playback, mic}] for each sound device."""
    cards = []
    for card in sorted(glob.glob("/proc/asound/card[0-9]*")):
        try:
            with open(os.path.join(card, "id")) as f:
                card_id = f.read().strip()
        except OSError:
            continue
        cards.append({
            "id": card_id,
            "usb": os.path.exists(os.path.join(card, "usbid")),
            "playback": sorted(int(os.path.basename(p)[3:-1]) for p in glob.glob(card + "/pcm*p")),
            "mic": bool(glob.glob(card + "/pcm*c")),
        })
    return cards


# --- Test (start.py --test-sound) ---

def test():
    """List the sound devices, say which is used, play a beep."""
    print("Sound devices:")
    for c in sound_cards() or [{"id": "(none found)", "usb": False, "playback": [], "mic": False}]:
        kind = "USB" if c["usb"] else "built in"
        parts = (["plays sound"] if c["playback"] else []) + (["has a mic"] if c["mic"] else [])
        note = " - not used: it has a mic" if c["usb"] and c["mic"] and c["playback"] else ""
        print(f"  {c['id']}: {kind}, {', '.join(parts) or 'nothing'}{note}")
    device, where = speaker()
    print(f'speaker = "{SPEAKER}" in settings.toml -> ' + (f"the {where} ({device})" if device else "no USB speaker found"))
    if not enabled():
        print('Sound is off (speaker = "none").')
        return
    beep = os.path.join(CACHE, "songs", "test-beep.wav")
    os.makedirs(os.path.dirname(beep), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=880:duration=1.5", "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", beep])
    start_player(beep, "a test beep")
    if _player:
        _player.wait()
        print("Done. Heard nothing? Turn it up: alsamixer (F6 picks the device), then sudo alsactl store")
