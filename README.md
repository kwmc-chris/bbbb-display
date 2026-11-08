# bbbb-display

Shows the birds a **BirdNET-Pi** hears on a **Pimoroni Inky Impression** e-ink screen (4" or 7.3"), on a Raspberry Pi 4. Each Pi runs one of two displays, chosen in its `settings.toml`:

- **full**: the latest bird with today's totals, plus browse pages (photo, facts, QR code to Wikipedia), using the buttons.
- **simple**: in portrait, the bird's everyday name (*Robin*, not *European Robin*), its whole photo across the width, and underneath a verse from a classic poem that mentions it.

Both can play BirdNET-Pi's own recording of the bird through a USB speaker (the song button, on the live screen or a browse page), and both can shut the Pi down from the buttons.

## Files

| | |
|---|---|
| `start.py` | Starts the display chosen in `settings.toml` |
| `settings.example.toml` | Example settings. `install.sh` copies it to `settings.toml` |
| `install.sh` | First-time setup on a new Pi: packages, screen, start at boot, nightly update |
| `update.sh` | Nightly update from GitHub |
| `requirements.txt` | Python packages |
| `full/` | The full display: `display.py` (live screen and buttons), `browse.py`, `info.py` (Wikipedia and Wikidata facts), `birdfacts.json` (your tile facts), `nophoto.jpg` |
| `simple/` | The simple display: `display.py`, `poems.py` (verses from [PoetryDB](https://poetrydb.org)), `birdnames.json` (name shown and poem search words) |
| `common/` | Shared by both: BirdNET-Pi's database, photos, birdsong, buttons, the screen |

Made on the Pi and not in GitHub: `settings.toml`, `.venv/`, `cache/` (downloaded photos, songs and poems, safe to delete), `display.log`, `update.log`.

Optional extras: `birds/` with your own photos named after the bird (e.g. `birds/European Robin.jpg`), and `full/icons/` with your own tile icons.

## Setting up a Pi

You need a new install of Raspberry Pi OS (Bookworm or later), a working [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi), and the Inky fitted.

**1. Download:**
```
cd /home/pi
git clone https://github.com/kwmc-chris/bbbb-display.git
cd bbbb-display
```

**2. Install:**
```
bash install.sh
```
Run this once, on a new Pi. It installs everything, switches on the screen connection, and sets the display to start at boot and update itself at night.

**3. Choose the display** and set anything else this Pi needs (speaker, buttons, screen rotation), then reboot:
```
nano settings.toml
sudo reboot
```
After changing `settings.toml` later: `sudo systemctl restart bbbb-display`.

**4. Try it by hand** (stop the service first so the screen is free):
```
sudo systemctl stop bbbb-display
.venv/bin/python start.py --once                      # latest bird, then stop
.venv/bin/python start.py --bird "European Robin"     # any bird
.venv/bin/python start.py --page browse               # full display: browse or sleep
.venv/bin/python start.py --test-buttons              # shows each button pressed
.venv/bin/python start.py --test-sound                # lists sound devices, plays a test beep
.venv/bin/python start.py                             # keep running (Ctrl+C stops)
sudo systemctl start bbbb-display
```
Add `--preview test.png` to save a picture instead of using the screen (no need to stop the service).

## Updates

Each Pi runs `update.sh` at 3am: it gets the latest version from GitHub and, if anything changed, updates the Python packages and restarts the display. To turn this off for a Pi, set `nightly_update = false` in its `settings.toml`. To update straight away:
```
bash update.sh --now
```
If the update log says a file was "edited on this Pi", put the file back with `git checkout <file>`. Keep changes for one Pi in `settings.toml`, which updates never touch.

## Settings

`settings.toml` has the settings you're most likely to change, with notes. Each `[section]` changes the settings at the top of one file, so you can change any other setting there too, written in lower case:

| Section | File |
|---|---|
| `[full]` | `full/display.py` |
| `[browse]` | `full/browse.py` |
| `[simple]` `[poems]` | `simple/display.py`, `simple/poems.py` |
| `[sound]` | `common/birdsong.py` |
| `[buttons]` | `common/buttons.py` |
| `[birdnet]` | `common/birdnet.py` (where BirdNET-Pi's database is) |

**Debug mode.** `debug = true` (near the top of `settings.toml`) is for testing: the display checks for birds every second and redraws for every new one. `DEBUG_SETTINGS` in `start.py` lists what it changes. Set it back to `false` afterwards.

**Sound.** The song button plays BirdNET-Pi's best recent recording of the bird on screen, if it still has one on disk (BirdNET-Pi deletes old recordings, so some birds have none). With `speaker = "auto"` it uses the USB speaker. A USB device with a mic is never used, so it can't pick the BirdNET mic. A new speaker may start quiet: run `alsamixer`, press F6 to pick it, turn it up, then `sudo alsactl store`. If it isn't working, `--test-sound` shows which device it picks and why, and the log shows any playing error.

**Buttons.** Each job (browse, live, song) has a GPIO pin. The Inky's own buttons are A = 5, B = 6, C = 16 and D = 24; C isn't used. Your own buttons connect a free pin (e.g. 4, 12, 13 or 26) to ground. Don't use 2, 3, 8, 9, 10, 11, 17, 22 or 27, because the screen needs them. Holding the two `shutdown` buttons for 3 seconds shuts the Pi down safely. On the full display the screen then shows "Sleeping since…". Unplug and replug the power to start it again.

**Birds.** `full/birdfacts.json` holds the browse tile facts. Birds not in it get facts from Wikidata. `simple/birdnames.json` gives each bird a short name and the words to search poems for, e.g. `"European Robin": {"name": "Robin", "search": ["robin", "redbreast"]}`.

## Useful commands

```
tail -f display.log                        # what the display is doing (Ctrl+C stops watching)
tail update.log                            # last night's update
sudo systemctl status bbbb-display         # is it running?
sudo systemctl restart bbbb-display        # restart, e.g. after changing settings.toml
```

## Credits

Photos: Wikimedia Commons or Flickr (credit shown on screen). Poems: PoetryDB (public domain). Birdsong: BirdNET-Pi's own recordings. Detections: BirdNET-Pi.
