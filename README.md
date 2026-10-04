# bbbb-display

BirdNET-Pi bird display on a Pimoroni Inky Impression 4" (Spectra 6, 600 × 400) e-ink screen, on a Raspberry Pi 4B (`birdnet-chloe`). Installed on the Pi in `/home/pi/bbbb-display`.

## Files

| File | Purpose |
|---|---|
| `bbbb-display.py` | Main script: watches for birds, live screen, buttons, switching screens |
| `birdinfo.py` | Descriptions, photos and tile facts (Wikipedia, Wikidata, Flickr, `birdfacts.json`); saves results |
| `birdbrowser.py` | Buttons and browse pages, including tile icons |
| `birdchart.py` | Today's species-by-hour chart |
| `birdqr.py` | QR codes on browse pages (needs the `qrcode` package – `update.sh` installs it) |
| `birdsong.py` | Plays the bird's song (button D): Wikimedia recording, else BirdNET-Pi's clip; levels the volume; picks USB speaker or headphone socket |
| `birdfacts.json` | Your tile facts for ~50 UK birds – edit to add or correct |
| `imagetest.jpg` | Shown when there's no bird photo |
| `rc.local` | Boot file; `update.sh` installs it as `/etc/rc.local` |
| `update.sh` | Installs updates on the Pi |
| `.gitignore` | Keeps Pi-generated files out of GitHub |

Created on the Pi (not in GitHub): `bird_photos/`, `birdinfo_*.json` (saved lookups), `display.log`. Safe to delete – they're rebuilt. Your own files: `birds/` (photos named after the bird, e.g. `European Robin.jpg`) and `icons/` (tile icon PNGs, e.g. `trees.png`).

## Screens and buttons

| Screen | Shows | Hints shown |
|---|---|---|
| Live | Latest bird, description, today's totals, recent birds, IP address | A browse, C data |
| Browse | Per species: photo, order/family, times heard, five tiles, description, QR code to its Wikipedia article | A next, B live, C data, D birdsong |
| Data | Today's species by hour | A browse, B live |

| Button | Does |
|---|---|
| **A** | Browse: first press shows the most recent species, each further press the next older one (back to the start after the oldest) |
| **B** | Back to the live screen |
| **C** | Data screen (pressed there: redraw it) |
| **D** | Browse pages only: play the bird's song; press again to stop |
| **A + D** held 3 s | Power off: the live screen shows "Sleeping since 16:05" (it stays visible with the power off), then the Pi shuts down safely. Unplug and replug the power to start it again |

Browse and data return to live after 5 minutes without a press. Hints are set by `BUTTON_HINTS` in `bbbb-display.py`.

**Birdsong** comes from the species' recording on Wikimedia Commons if there is one, otherwise BirdNET-Pi's own clip (only while it's still on disk). Every clip is levelled with ffmpeg – rumble removed, brought to the same loudness, peaks limited, trimmed to 20 s – and saved in `bird_songs/`, so the first press for a bird takes a moment longer. It plays through a USB speaker if one is plugged in (not the mic adapter), otherwise the 3.5 mm headphone socket. The Pi's default sound device isn't changed, as BirdNET-Pi records through it.

## Setting up a new Pi

1. Install Raspberry Pi OS and [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi), and check BirdNET-Pi is detecting birds.
2. Install Pimoroni's Inky software (answer its questions), then reboot:
   ```
   git clone https://github.com/pimoroni/inky ~/inky
   cd ~/inky && ./install.sh
   sudo reboot
   ```
3. Download this project and run the installer:
   ```
   cd /home/pi
   git clone https://github.com/kwmc-chris/bbbb-display.git
   cd bbbb-display && bash update.sh
   ```
   It installs the `qrcode` package and an audio player if needed, switches on the headphone socket and sets its volume, and sets the display to start at boot. If it says a reboot is needed, run `sudo reboot`.

## Updating

1. **Mac:** put the changed files in the repository folder → GitHub Desktop → **Commit** → **Push**.
2. **Pi:**
   ```
   cd /home/pi/bbbb-display
   bash update.sh
   ```
   Steps: (1) pull from GitHub, (2) check files and Python packages, (3) set up sound, (4) stop the display, (5) install `rc.local` if changed (old one backed up in `/etc`), (6) test the database, (7) draw the live screen once, (8) start the display and show the live log. **Ctrl+C** stops watching the log; the display keeps running. Run without `sudo`. Options: `--no-pull`, `--no-log`, `--no-start`.

`HEADPHONE_VOLUME` at the top of `update.sh` sets the headphone volume at each update (`""` to leave it alone).

Edit `birdfacts.json` on the Mac, not the Pi – a file changed on the Pi makes `git pull` stop.

## Useful commands (on the Pi)

```
source ~/.virtualenvs/pimoroni/bin/activate      # needed before running scripts by hand
sudo pkill -f bbbb-display.py               # stop the running display first
python3 bbbb-display.py --help              # all options
python3 bbbb-display.py --once              # draw the live screen once
python3 bbbb-display.py --browse 0          # draw the first browse page
python3 bbbb-display.py --chart             # draw the chart
python3 bbbb-display.py --sleep-screen      # draw the "sleeping" screen (doesn't shut down)
  ... --preview test.png                         # save a PNG instead of using the screen
python3 birdinfo.py "European Robin" "Erithacus rubecula" --refresh   # test lookups for a bird
python3 birdbrowser.py --test-buttons            # print button presses
python3 birdbrowser.py --icon-sheet icons.png    # all icons on their tiles
python3 birdqr.py "https://example.com" --preview qr.png   # test a QR code
python3 birdsong.py --output                     # which speaker birdsong will use
python3 birdsong.py "European Robin" "Erithacus rubecula"   # play the song now
tail -f display.log                              # watch the log (Ctrl+C to stop watching)
```

## Settings

Each script has a **SETTINGS** section at the top. Main ones in `bbbb-display.py` (most can also be given on the command line – see `--help`):

| Setting | Default | Option |
|---|---|---|
| `POLL_SECONDS` – check for new birds | 30 | `--poll` |
| `MIN_REFRESH_SECONDS` – min gap between live redraws | 180 | `--min-refresh` |
| `BROWSE_TIMEOUT_SECONDS` – idle time before back to live | 300 | `--browse-timeout` |
| `ROTATE` – 180 if upside down | 0 | `--rotate` |
| `SATURATION` – photo colour 0–1 | 0.5 | `--saturation` |
| `CHART_STYLE` – `drawn` or `birdnet` | drawn | `--chart-style` |
| `SHOW_QR` – QR code on browse pages | True | `--no-qr` |
| `SHOW_BUTTON_HINTS`, `BUTTON_HINTS` – button hints on each screen | on | – |
| `SHUTDOWN_ENABLED`, `SHUTDOWN_HOLD_SECONDS`, `SLEEP_TEXT` – power off with A + D | on, 3, `Sleeping since %H:%M` | – |

In `birdbrowser.py`: `DESCRIPTION_LINES` (4), `TILE_COLOURS`, `PAGE_FONTS`, icon `KEYWORDS`. In `birdchart.py`: `COUNT_COLOURS`. In `birdqr.py`: `MODULE_SIZES`, `ERROR_CORRECTION`. In `birdsong.py`: `LOUDNESS` (-20; e.g. -16 louder, -24 quieter), `SONG_SOURCES` (order: `wikimedia`, `birdnet`), `CLIP_SECONDS`, `HIGHPASS_HZ`, `RECORDING_CHOICE`, `AUDIO_OUTPUT`. Changing the mastering settings prepares fresh clips automatically.

## Adding a bird to `birdfacts.json`

Copy an existing line and change it. The key is the scientific name exactly as BirdNET reports it. Keep values to 1–3 words; `uk_status` is `"Red"`, `"Amber"`, `"Green"` or `null`. Every line except the last needs a comma. Check with `python3 -m json.tool birdfacts.json` (`update.sh` also checks it).

## Troubleshooting

| Problem | Try |
|---|---|
| Screen not updating | `tail -n 30 display.log` (check the timestamps are recent) |
| "Device or resource busy" | Another copy is running: `sudo pkill -f bbbb-display.py` |
| Buttons do nothing | Stop the display, then `python3 birdbrowser.py --test-buttons` |
| No photo or description | `python3 birdinfo.py "Name" "Scientific name" --refresh` |
| A + D hold doesn't power off | The log shows why. "Shutdown failed": the user needs `sudo` without a password (normal on Raspberry Pi OS) |
| No QR codes | Needs the `qrcode` package – `update.sh` installs it; check its step 2 |
| No birdsong | `python3 birdsong.py "Name" "Scientific name"` shows where it fails; `--output` shows the speaker; `--check` checks ffmpeg and aplay. Test the socket: `speaker-test -D plughw:CARD=Headphones,DEV=0 -c 2 -t wav -l 1` |
| Birdsong too loud/quiet | `LOUDNESS` in `birdsong.py` (all clips), or `HEADPHONE_VOLUME` in `update.sh` (the socket) |
| `git pull` stops: "local changes" | A file was edited on the Pi. `git status` shows which; `git checkout -- FILE` discards the Pi's edit |
