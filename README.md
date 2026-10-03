# bbbb-display

BirdNET-Pi bird display on a Pimoroni Inky Impression 4" (Spectra 6, 600 × 400) e-ink screen, on a Raspberry Pi 4B (`birdnet-chloe`). Installed on the Pi in `/home/pi/bbbb/custom_display`.

## Files

| File | Purpose |
|---|---|
| `bbbb-display.py` | Main script: watches for birds, live screen, buttons, switching screens |
| `birdinfo.py` | Descriptions, photos and tile facts (Wikipedia, Wikidata, Flickr, `birdfacts.json`); saves results |
| `birdbrowser.py` | Buttons and browse pages, including tile icons |
| `birdchart.py` | Today's species-by-hour chart |
| `birdfacts.json` | Your tile facts for ~50 UK birds – edit to add or correct |
| `imagetest.jpg` | Shown when there's no bird photo |
| `rc.local` | Boot file; `update.sh` installs it as `/etc/rc.local` |
| `update.sh` | Installs updates on the Pi |
| `.gitignore` | Keeps Pi-generated files out of GitHub |

Created on the Pi (not in GitHub): `bird_photos/`, `birdinfo_*.json` (saved lookups), `display.log`. Safe to delete – they're rebuilt. Your own files: `birds/` (photos named after the bird, e.g. `European Robin.jpg`) and `icons/` (tile icon PNGs, e.g. `trees.png`).

## Screens and buttons

| Screen | Shows | Button |
|---|---|---|
| Live | Latest bird, description, today's totals, recent birds, IP address | **B** (from anywhere) |
| Browse | Per species: photo, order/family, times heard, five tiles, description | **A** previous / **D** next |
| Chart | Today's species by hour | **C** (again to redraw) |

Browse and chart return to live after 5 minutes without a press.

## Updating

1. **Mac:** put the changed files in the repository folder → GitHub Desktop → **Commit** → **Push**.
2. **Pi:**
   ```
   cd /home/pi/bbbb/custom_display
   bash update.sh
   ```
   It pulls from GitHub, checks the files, stops the display, installs `rc.local` if changed (old one backed up in `/etc`), tests the database, draws the live screen once, then asks whether to start the display. Run without `sudo`.

Edit `birdfacts.json` on the Mac, not the Pi – a file changed on the Pi makes `git pull` stop.

## Useful commands (on the Pi)

```
source ~/.virtualenvs/pimoroni/bin/activate      # needed before running scripts by hand
sudo pkill -f bbbb-display.py               # stop the running display first
python3 bbbb-display.py --help              # all options
python3 bbbb-display.py --once              # draw the live screen once
python3 bbbb-display.py --browse 0          # draw the first browse page
python3 bbbb-display.py --chart             # draw the chart
  ... --preview test.png                         # save a PNG instead of using the screen
python3 birdinfo.py "European Robin" "Erithacus rubecula" --refresh   # test lookups for a bird
python3 birdbrowser.py --test-buttons            # print button presses
python3 birdbrowser.py --icon-sheet icons.png    # all icons on their tiles
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

In `birdbrowser.py`: `DESCRIPTION_LINES` (2), `TILE_COLOURS`, `PAGE_FONTS`, icon `KEYWORDS`. In `birdchart.py`: `COUNT_COLOURS`.

## Adding a bird to `birdfacts.json`

Copy an existing line and change it. The key is the scientific name exactly as BirdNET reports it. Keep values to 1–3 words; `uk_status` is `"Red"`, `"Amber"`, `"Green"` or `null`. Every line except the last needs a comma. Check with `python3 -m json.tool birdfacts.json` (`update.sh` also checks it).

## Troubleshooting

| Problem | Try |
|---|---|
| Screen not updating | `tail -n 30 display.log` (check the timestamps are recent) |
| "Device or resource busy" | Another copy is running: `sudo pkill -f bbbb-display.py` |
| Buttons do nothing | Stop the display, then `python3 birdbrowser.py --test-buttons` |
| No photo or description | `python3 birdinfo.py "Name" "Scientific name" --refresh` |
| `git pull` stops: "local changes" | A file was edited on the Pi. `git status` shows which; `git checkout -- FILE` discards the Pi's edit |
