# bbbb-display

Shows the birds a **BirdNET-Pi** hears on a **Pimoroni Inky Impression** e-ink screen (4" or 7.3"), on a Raspberry Pi 4. Each Pi runs one of two displays, chosen in its `settings.toml`:

- **full**: the latest bird with today's totals, plus browse pages (photo, facts, QR code to Wikipedia), using the buttons.
- **simple**: in portrait, the bird's everyday name (*Robin*, not *European Robin*), its whole photo across the width, and underneath a verse from a classic poem that mentions it, with the IP address and update time along the bottom.

Both can play BirdNET-Pi's own recording of the bird through a USB speaker (the song button, on the live screen or a browse page), and both can shut the Pi down from the buttons.

## Files

| | |
|---|---|
| `start.py` | Starts the display chosen in `settings.toml` |
| `settings.example.toml` | Example settings. `install.sh` copies it to `settings.toml` |
| `install.sh` | First-time setup on a new Pi: packages, screen, start at boot, nightly update |
| `update.sh` | Nightly update from GitHub |
| `requirements.txt` | Python packages |
| `full/` | The full display: `display.py` (live screen and buttons), `browse.py`, `info.py` (Wikipedia and Wikidata facts), `nophoto.jpg` |
| `simple/` | The simple display: `display.py`, `poems.py` (verses from [PoetryDB](https://poetrydb.org)) |
| `common/` | Shared by both: BirdNET-Pi's database, photos, birdsong, buttons, the screen, and `birdinfo.json` (your names and facts for each bird) |

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

**3. Choose the display** and the screen rotation, then reboot:
```
nano settings.toml
sudo reboot
```
After changing `settings.toml` later: `sudo systemctl restart bbbb-display`.

## Updates

Each Pi runs `update.sh` at 3am: it gets the latest version from GitHub and, if anything changed, updates the Python packages and restarts the display. To turn this off for a Pi, set `nightly_update = false` in its `settings.toml`. To update straight away:
```
bash update.sh --now
```
If the update log says a file was "edited on this Pi", put the file back with `git checkout <file>`. Keep changes for one Pi in `settings.toml`, which updates never touch.

## Settings

`settings.toml` has the settings for this Pi, with notes. `[full]` and `[simple]` can also change any other setting at the top of `full/display.py` or `simple/display.py`, written in lower case. Everything else is set at the top of its own file.

**Debug mode.** `debug = true` (near the top of `settings.toml`) is for testing: the display checks for birds every second and redraws for every new one. `DEBUG_SETTINGS` in `start.py` lists what it changes. Set it back to `false` afterwards.

**Sound.** The song button plays BirdNET-Pi's best recent recording of the bird on screen through the USB speaker, if it still has one on disk (BirdNET-Pi deletes old recordings, so some birds have none). A USB device with a mic is never used, so it can't pick the BirdNET mic. A new speaker may start quiet: run `alsamixer`, press F6 to pick it, turn it up, then `sudo alsactl store`. Any playing error is in `display.log`.

**Updated and sleeping.** Both displays show the IP address and when the screen was last updated (e.g. "Updated Mon 18:22") along the bottom. The IP address is checked every 10 minutes, and if it changes (e.g. to "No network") the screen is redrawn. When the Pi shuts down or reboots (the shutdown buttons, `sudo shutdown` or `sudo reboot`), the screen changes to "Sleeping since Mon 18:30" in red first. An e-ink screen keeps its picture without power, so after a power cut it still shows the last update time: if that's old, the Pi is off.

**Buttons.** The Inky's own buttons: A = browse, B = live, D = song (C isn't used); the pins are in `common/buttons.py`. Holding A and D together for 3 seconds shuts the Pi down safely. Unplug and replug the power to start it again.

**Birds.** `common/birdinfo.json` has an entry for each bird, under BirdNET-Pi's name for it:
```
"European Robin": {
  "sci": "Erithacus rubecula", "short_name": "Robin", "search": ["robin", "redbreast"],
  "habitat": "Gardens", "food": "Insects", "nesting": "Cavity", "behavior": "Ground Forager", "uk_status": "Green",
  "order": "Passeriformes", "family": "Muscicapidae", "family_name": "Old World Flycatchers"
}
```
`sci` also finds the bird when BirdNET-Pi uses another name for it. `short_name` and `search` are for the simple display: the name shown and the words to search poems for. The rest are the browse page tiles on the full display. Every field is optional. Birds not listed get a short name without words like "European", and tile facts from Wikidata.

## Useful commands

```
tail -f display.log                        # what the display is doing (Ctrl+C stops watching)
tail update.log                            # last night's update
sudo systemctl status bbbb-display         # is it running?
sudo systemctl restart bbbb-display        # restart, e.g. after changing settings.toml
```

## Credits

Photos: Wikimedia Commons (credit shown on screen). Poems: PoetryDB (public domain). Birdsong: BirdNET-Pi's own recordings. Detections: BirdNET-Pi.
