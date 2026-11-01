"""Plays a bird's song through a speaker.

The recording comes from Wikimedia Commons (good field recordings), or else
BirdNET-Pi's own clip of the bird if it's still on disk. Each clip is cleaned
up with ffmpeg: rumble removed, brought to the same loudness, trimmed to
CLIP_SECONDS. Results are kept in cache/songs/.

    toggle(com_name, sci_name)   play the song, or stop it if playing
"""

import glob
import hashlib
import os
import re
import shutil
import subprocess
import urllib.parse

from common import CACHE, birdnet, web

# "auto" = a USB speaker if one's plugged in, otherwise the headphone socket.
# Or "headphones", "none" (no sound), or an ALSA device name.
SPEAKER = "auto"

LOUDNESS = -20          # LUFS: higher (e.g. -16) = louder, lower (-24) = quieter
PEAK_LIMIT = -2         # loudest peak allowed (dBTP)
HIGHPASS_HZ = 250       # cut rumble below this; 0 = off
CLIP_SECONDS = 20       # longest clip played (fades out at the end)

_player = None          # aplay, while playing


def enabled():
    return SPEAKER != "none"


def toggle(com_name, sci_name=None):
    """Stop if playing, otherwise find, prepare and play the song."""
    if is_playing():
        stop()
        print("Birdsong stopped.")
    else:
        play(com_name, sci_name)


def play(com_name, sci_name=None):
    stop()
    if not enabled():
        return
    missing = [t for t in ("ffmpeg", "aplay") if not shutil.which(t)]
    if missing:
        print(f"Can't play birdsong - missing {', '.join(missing)} (install.sh installs them)")
        return
    path, credit = get_song(com_name, sci_name)
    if not path:
        print(f"No recording of {com_name} found.")
        return
    device, where = speaker()
    global _player
    _player = subprocess.Popen(["aplay", "-q", "-D", device, path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Playing {com_name} ({credit}) through the {where}")


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


# --- Finding a recording ---

def get_song(com_name, sci_name=None):
    """(prepared .wav file, credit), or (None, None)."""
    folder = os.path.join(CACHE, "songs")
    tag = hashlib.md5(f"{LOUDNESS}{PEAK_LIMIT}{HIGHPASS_HZ}{CLIP_SECONDS}".encode()).hexdigest()[:6]

    url, credit = wikimedia_song(com_name, sci_name)
    if url:
        out = os.path.join(folder, f"{web.slug(com_name)}_{tag}.wav")
        if os.path.exists(out) or prepare(url, out):
            return out, credit

    clip = birdnet_clip(com_name)
    if clip:
        out = os.path.join(folder, "birdnet", f"{web.slug(os.path.basename(clip))}_{tag}.wav")
        if os.path.exists(out) or prepare(clip, out):
            old = sorted(glob.glob(os.path.join(folder, "birdnet", "*.wav")), key=os.path.getmtime)
            for f in old[:-50]:                 # keep the newest 50
                os.remove(f)
            return out, "BirdNET-Pi recording"
    return None, None


def wikimedia_song(com_name, sci_name=None):
    """(url, credit) of the bird's recording on Wikimedia Commons, or (None, None).
    Lookups are saved, including "none found"."""
    saved_file = os.path.join(CACHE, "songs", "sources.json")
    saved = web.load_json(saved_file)
    if com_name in saved:
        return saved[com_name]["url"], saved[com_name]["credit"]
    filename = None
    try:
        for title in filter(None, (sci_name, com_name)):
            filename = wikidata_audio(title) or article_audio(title)
            if filename:
                break
    except Exception as e:
        print(f"Couldn't look up a recording ({e})")
        return None, None                       # offline: try again next time
    url = credit = None
    if filename:
        url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
               + urllib.parse.quote(filename.replace(" ", "_")))
        credit = web.commons_credit(filename)
    saved[com_name] = {"url": url, "credit": credit}
    web.save_json(saved_file, saved)
    return url, credit


def wikidata_audio(title):
    """Audio file from the bird's Wikidata entry (property P51), or None."""
    data = web.get_json(f"https://{web.WIKI_LANG}.wikipedia.org/w/api.php?action=query"
                        "&format=json&prop=pageprops&ppprop=wikibase_item&redirects=1&titles="
                        + urllib.parse.quote(title))
    qid = next(iter(data["query"]["pages"].values())).get("pageprops", {}).get("wikibase_item")
    if not qid:
        return None
    entity = web.get_json("https://www.wikidata.org/w/api.php?action=wbgetentities"
                          "&format=json&props=claims&ids=" + qid)["entities"][qid]
    for claim in entity.get("claims", {}).get("P51", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if value:
            return value
    return None


def article_audio(title):
    """First audio file in the bird's Wikipedia article, or None."""
    data = web.get_json(f"https://{web.WIKI_LANG}.wikipedia.org/api/rest_v1/page/media-list/"
                        + urllib.parse.quote(title.replace(" ", "_")))
    for item in data.get("items", []):
        if item.get("type") == "audio" and item.get("title"):
            return item["title"].split(":", 1)[-1]          # "File:X.ogg" -> "X.ogg"
    return None


def birdnet_clip(com_name):
    """BirdNET-Pi's best recent clip of the bird that's still on disk, or None."""
    rows = birdnet.query("SELECT Date, File_Name, Confidence FROM detections WHERE Com_Name = ? "
                         "ORDER BY Date DESC, Time DESC LIMIT 50", com_name)
    conf = birdnet.config()
    folder = conf.get("EXTRACTED", "") or "~/BirdSongs/Extracted"
    names = dict(conf, HOME=os.path.expanduser("~"))
    for _ in range(3):                          # expand ${RECS_DIR} etc.
        folder = re.sub(r"\$\{?(\w+)\}?", lambda m: names.get(m.group(1), m.group(0)), folder)
    base = os.path.join(os.path.expanduser(folder), "By_Date")
    for row in sorted(rows, key=lambda r: -float(r["Confidence"] or 0)):
        if row["File_Name"]:
            found = glob.glob(os.path.join(base, row["Date"], "*", row["File_Name"]))
            if found:
                return found[0]
    return None


def prepare(source, out):
    """Clean up and level a clip (file or web address) with ffmpeg."""
    filters = ([f"highpass=f={HIGHPASS_HZ}"] if HIGHPASS_HZ else []) + [
        f"loudnorm=I={LOUDNESS}:TP={PEAK_LIMIT}:LRA=11", "afade=t=in:d=0.05",
        f"afade=t=out:st={max(CLIP_SECONDS - 1.5, 0)}:d=1.5"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if source.startswith("http"):
        cmd += ["-user_agent", web.USER_AGENT, "-rw_timeout", str(web.TIMEOUT * 1_000_000)]
    cmd += ["-i", source, "-t", str(CLIP_SECONDS), "-af", ",".join(filters),
            "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", out]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(out):
        print(f"Couldn't prepare the recording: {result.stderr.strip()[:200]}")
        return False
    return True


# --- Choosing the speaker ---

def speaker():
    """(ALSA device, description) to play through, following SPEAKER."""
    if SPEAKER not in ("auto", "headphones"):
        return SPEAKER, SPEAKER
    cards = sound_cards()
    if SPEAKER == "auto":
        for c in cards:            # USB speaker = USB sound card without a mic (not BirdNET's mic)
            if c["usb"] and c["playback"] and not c["mic"]:
                return f"plughw:CARD={c['id']},DEV={c['playback'][0]}", f"USB speaker ({c['id']})"
    for c in cards:
        if c["id"] == "Headphones" and c["playback"]:
            return f"plughw:CARD=Headphones,DEV={c['playback'][0]}", "headphone socket"
    return "default", "default sound device"


def sound_cards():
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
