#!/usr/bin/env python3
"""
birdsong.py - plays a bird's song for bbbb-display.py (button D).

    toggle(db, name, sci)   play the song, or stop if already playing

Where the song comes from (SONG_SOURCES, tried in order):
    "wikimedia"  the species' recording on Wikimedia Commons (via Wikidata,
                 or the Wikipedia article) - mostly good-quality field recordings
    "birdnet"    BirdNET-Pi's own clip of a detection (only while still on disk)

Every clip is "mastered" with ffmpeg before playing: low rumble removed,
brought to the same loudness (LOUDNESS), peaks limited, trimmed to
CLIP_SECONDS with a fade-out. Results are saved in bird_songs/, so each is
only prepared once.

Plays with aplay, through a USB speaker if plugged in (a USB device with a
mic input, e.g. the BirdNET-Pi mic adapter, doesn't count), otherwise the
3.5 mm headphone socket. The Pi's default sound device is not changed.

Test:  python3 birdsong.py "European Robin" "Erithacus rubecula"   play it
       python3 birdsong.py --output      which speaker would be used
       python3 birdsong.py --check       ffmpeg and aplay installed?
"""

# =============================================================================
# SETTINGS
# =============================================================================

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.expanduser("~/BirdNET-Pi/scripts/birds.db")
SONG_DIR = os.path.join(SCRIPT_DIR, "bird_songs")      # prepared clips

SONG_SOURCES = ["wikimedia", "birdnet"]   # tried in this order

# Mastering
LOUDNESS = -20          # target loudness in LUFS: higher (e.g. -16) = louder, lower (-24) = quieter
PEAK_LIMIT = -2         # loudest peak allowed, dBTP
HIGHPASS_HZ = 250       # remove rumble below this (birds sing higher); 0 = off
CLIP_SECONDS = 20       # longest clip played (fades out at the end)

# BirdNET-Pi's own clips
RECORDING_CHOICE = "best"     # "best" = highest confidence, "latest" = most recent
RECORDINGS_CHECKED = 50
CONF_PATHS = ["/etc/birdnet/birdnet.conf", os.path.expanduser("~/BirdNET-Pi/birdnet.conf")]
DEFAULT_EXTRACTED = os.path.expanduser("~/BirdSongs/Extracted")

# Output: "auto" = USB speaker (USB output with no mic input) if plugged in,
# else headphone socket. Or a fixed ALSA device, e.g. "plughw:CARD=Headphones,DEV=0"
AUDIO_OUTPUT = "auto"
HEADPHONE_CARD = "Headphones"
ASOUND_DIR = "/proc/asound"

# Internet (Wikimedia)
WIKI_LANG = "en"
USER_AGENT = "birdnet-inky-display/1.0 (personal Raspberry Pi bird display)"
TIMEOUT = 15

# =============================================================================

import glob
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import urllib.parse
import urllib.request
from html import unescape

_process = None               # aplay while playing
SOURCES_FILE = os.path.join(SONG_DIR, "sources.json")   # Wikimedia lookups + credits

# --- Small helpers -------------------------------------------------------------

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _slug(name):
    return re.sub(r"\W+", "_", name).strip("_")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

# --- Source 1: Wikimedia Commons -------------------------------------------------

def _wikidata_audio(title):
    """Audio file name from the species' Wikidata entry (property P51), or None."""
    data = _get_json(f"https://{WIKI_LANG}.wikipedia.org/w/api.php?action=query&format=json"
                     "&prop=pageprops&ppprop=wikibase_item&redirects=1&titles="
                     + urllib.parse.quote(title))
    page = next(iter(data["query"]["pages"].values()))
    qid = page.get("pageprops", {}).get("wikibase_item")
    if not qid:
        return None
    entity = _get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
                       "&props=claims&ids=" + qid)["entities"][qid]
    for claim in entity.get("claims", {}).get("P51", []):
        try:
            return claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
    return None


def _article_audio(title):
    """First audio file used in the Wikipedia article, or None."""
    data = _get_json(f"https://{WIKI_LANG}.wikipedia.org/api/rest_v1/page/media-list/"
                     + urllib.parse.quote(title.replace(" ", "_")))
    for item in data.get("items", []):
        if item.get("type") == "audio" and item.get("title"):
            return item["title"].split(":", 1)[-1]       # "File:X.ogg" -> "X.ogg"
    return None


def _commons_credit(filename):
    """"Recordist / Wikimedia Commons (licence)"."""
    try:
        data = _get_json("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                         "&prop=imageinfo&iiprop=extmetadata&titles=File:"
                         + urllib.parse.quote(filename))
        meta = next(iter(data["query"]["pages"].values()))["imageinfo"][0]["extmetadata"]
        strip = lambda t: re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", t or ""))).strip()
        artist = strip(meta.get("Artist", {}).get("value"))
        licence = strip(meta.get("LicenseShortName", {}).get("value"))
        if artist:
            return f"{artist} / Wikimedia Commons" + (f" ({licence})" if licence else "")
    except Exception:
        pass
    return "Wikimedia Commons"


def wikimedia_song(com_name, sci_name=None, refresh=False):
    """(url, credit) of the species' Commons recording, or (None, None).
    Lookups are saved, including "none found", until refresh=True."""
    sources = _load_json(SOURCES_FILE)
    if not refresh and com_name in sources:
        entry = sources[com_name]
        return entry.get("url"), entry.get("credit")
    filename = None
    try:
        for title in filter(None, (sci_name, com_name)):
            filename = _wikidata_audio(title) or _article_audio(title)
            if filename:
                break
    except Exception as e:
        print(f"Couldn't look up a Wikimedia recording ({e})")
        return None, None                         # offline: try again next time
    url = credit = None
    if filename:
        url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
               + urllib.parse.quote(filename.replace(" ", "_")))
        credit = _commons_credit(filename)
    sources[com_name] = {"url": url, "credit": credit}
    _save_json(SOURCES_FILE, sources)
    return url, credit

# --- Source 2: BirdNET-Pi's own clips ------------------------------------------------

def birdnet_config():
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
    """Where BirdNET-Pi keeps its clips (expands ${RECS_DIR}, $HOME, ~)."""
    conf = birdnet_config()
    value = conf.get("EXTRACTED", "")
    if not value:
        return DEFAULT_EXTRACTED
    names = dict(conf, HOME=os.path.expanduser("~"))
    for _ in range(3):
        value = re.sub(r"\$\{?(\w+)\}?", lambda m: names.get(m.group(1), m.group(0)), value)
    return os.path.expanduser(value)


def find_recording(db_path, com_name):
    """A BirdNET-Pi clip of the species still on disk, or None."""
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
    folder = com_name.replace("'", "").replace(" ", "_")
    for date, file_name, _ in rows:
        if not file_name:
            continue
        path = os.path.join(base, date, folder, file_name)
        if os.path.isfile(path):
            return path
        matches = glob.glob(os.path.join(base, date, "*", file_name))
        if matches:
            return matches[0]
    return None

# --- Mastering -------------------------------------------------------------------------

def master(source, out_path):
    """Clean up and level a clip with ffmpeg; source = file or web address.
    Returns True if out_path was made."""
    filters = []
    if HIGHPASS_HZ:
        filters.append(f"highpass=f={HIGHPASS_HZ}")
    filters += [f"loudnorm=I={LOUDNESS}:TP={PEAK_LIMIT}:LRA=11",
                "afade=t=in:d=0.05",
                f"afade=t=out:st={max(CLIP_SECONDS - 1.5, 0)}:d=1.5"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if source.startswith("http"):
        cmd += ["-user_agent", USER_AGENT, "-rw_timeout", str(TIMEOUT * 1_000_000)]
    cmd += ["-i", source, "-t", str(CLIP_SECONDS), "-af", ",".join(filters),
            "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", out_path]
    os.makedirs(SONG_DIR, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(out_path):
        print(f"Couldn't prepare the clip ({result.stderr.strip()[:200]})")
        return False
    return True


def _settings_tag():
    """Short code for the mastering settings, so changing them makes new files."""
    text = f"{LOUDNESS}{PEAK_LIMIT}{HIGHPASS_HZ}{CLIP_SECONDS}"
    return hashlib.md5(text.encode()).hexdigest()[:6]


def get_song(db_path, com_name, sci_name=None):
    """(prepared .wav path, description of where it came from), or (None, None)."""
    for source in SONG_SOURCES:
        if source == "wikimedia":
            url, credit = wikimedia_song(com_name, sci_name)
            if not url:
                continue
            out = os.path.join(SONG_DIR, f"{_slug(com_name)}_wikimedia_{_settings_tag()}.wav")
            if os.path.exists(out) or master(url, out):
                return out, credit
        elif source == "birdnet":
            clip = find_recording(db_path, com_name)
            if not clip:
                continue
            name = os.path.splitext(os.path.basename(clip))[0]
            out = os.path.join(SONG_DIR, f"birdnet_{_slug(name)}_{_settings_tag()}.wav")
            if os.path.exists(out) or master(clip, out):
                _tidy_birdnet_clips()
                return out, "BirdNET-Pi recording"
    return None, None


def _tidy_birdnet_clips(keep=50):
    """Keep only the newest prepared BirdNET-Pi clips (they're always changing)."""
    files = sorted(glob.glob(os.path.join(SONG_DIR, "birdnet_*.wav")), key=os.path.getmtime)
    for f in files[:-keep]:
        os.remove(f)

# --- Choosing the speaker --------------------------------------------------------------

def sound_cards():
    """[{id, name, usb, playback_devices, capture}] for each sound card."""
    cards, descriptions = [], {}
    for line in _read(os.path.join(ASOUND_DIR, "cards")).splitlines():
        m = re.match(r"\s*(\d+)\s+\[.*?\]:\s*.*? - (.*)", line)
        if m:
            descriptions[m.group(1)] = m.group(2).strip()
    for card_dir in sorted(glob.glob(os.path.join(ASOUND_DIR, "card[0-9]*"))):
        number = os.path.basename(card_dir)[4:]
        cards.append({
            "id": _read(os.path.join(card_dir, "id")) or number,
            "name": descriptions.get(number, ""),
            "usb": os.path.exists(os.path.join(card_dir, "usbid")),
            "playback_devices": sorted(int(os.path.basename(p)[3:-1])          # pcm0p -> 0
                                       for p in glob.glob(os.path.join(card_dir, "pcm*p"))),
            "capture": bool(glob.glob(os.path.join(card_dir, "pcm*c"))),     # has a mic input
        })
    return cards


def choose_output():
    """(ALSA device, description): USB speaker, else headphone socket, else default."""
    if AUDIO_OUTPUT != "auto":
        return AUDIO_OUTPUT, "set in AUDIO_OUTPUT"
    cards = sound_cards()
    for card in cards:
        if card["usb"] and card["playback_devices"] and not card["capture"]:
            return (f"plughw:CARD={card['id']},DEV={card['playback_devices'][0]}",
                    f"USB speaker ({card['name'] or card['id']})")
    for card in cards:
        if card["id"] == HEADPHONE_CARD and card["playback_devices"]:
            return (f"plughw:CARD={HEADPHONE_CARD},DEV={card['playback_devices'][0]}",
                    "3.5 mm headphone socket")
    return "default", "default sound device"

# --- Playing ---------------------------------------------------------------------------

def missing_tools():
    return [t for t in ("ffmpeg", "aplay") if not shutil.which(t)]


def play(wav_path):
    """Start playing in the background. Returns True if it started."""
    global _process
    stop()
    if not shutil.which("aplay"):
        print("aplay not found - install it with: sudo apt install alsa-utils")
        return False
    device, description = choose_output()
    cmd = ["aplay", "-q"] + (["-D", device] if device != "default" else []) + [wav_path]
    _process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Playing through the {description}")
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


def toggle(db_path, com_name, sci_name=None):
    """Button D: stop if playing, otherwise prepare and play the song."""
    if is_playing():
        stop()
        print("Birdsong stopped.")
        return
    missing = missing_tools()
    if missing:
        print(f"Can't play birdsong - missing: {', '.join(missing)} (update.sh installs them)")
        return
    path, credit = get_song(db_path, com_name, sci_name)
    if not path:
        print(f"No recording of {com_name} found.")
        return
    print(f"Birdsong for {com_name}: {credit}")
    play(path)


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        missing = missing_tools()
        print("ffmpeg and aplay found" if not missing else "missing: " + ", ".join(missing))
    elif "--output" in sys.argv:
        device, description = choose_output()
        print(f"{description}  [{device}]")
    else:
        names = [a for a in sys.argv[1:] if not a.startswith("--")]
        if not names:
            raise SystemExit('Usage: python3 birdsong.py "Common Name" ["Scientific name"]'
                             '   (or --output, --check)')
        toggle(DATABASE, names[0], names[1] if len(names) > 1 else None)
        if _process:
            _process.wait()
