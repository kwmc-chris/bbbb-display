#!/bin/bash
# =============================================================================
# update.sh - install or update the BirdNET-Pi display (works on a new Pi too)
#
# Steps: 1 git pull   2 check files, install missing Python packages
#        3 sound for birdsong: audio player, headphone socket on, volume
#        4 stop the display   5 install rc.local (if changed; old one backed up)
#        6 database test   7 demo (--once)   8 start the display, show the log
#
# Run from this folder, without sudo:
#   bash update.sh              full update (Ctrl+C at the end stops watching
#                               the log - the display keeps running)
#   bash update.sh --no-pull    use the files already here
#   bash update.sh --no-log     don't show the log at the end
#   bash update.sh --no-start   don't start the display at the end
# =============================================================================

# --- Settings ---
MAIN="bbbb-display.py"
VENV_PYTHON="/home/pi/.virtualenvs/pimoroni/bin/python3"
RC_TARGET="/etc/rc.local"
STOP_TIMEOUT=15
HEADPHONE_VOLUME="100%"          # set at every update; "" = leave the volume alone
CONFIG_FILES="/boot/firmware/config.txt /boot/config.txt"   # Pi settings file (first found)
SOUND_CARDS="/proc/asound/cards"
# Python running the display - this or the old numbered versions
# (matching "python" leaves e.g. an open "nano bbbb-display.py" alone)
RUNNING_PATTERN='python3? .*(bbbb-display|birdnet_display[0-9]+)\.py'

# --- Helpers ---
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
step() { echo; echo "=== $* ==="; }
ok()   { echo "  ✓ $*"; }
note() { echo "  - $*"; }
warn() { echo "  ! $*"; }
fail() { echo; echo "  ✗ $*"; echo; echo "Update stopped."; exit 1; }

DO_PULL=1
START=yes
SHOW_LOG=yes
for arg in "$@"; do
    case "$arg" in
        --no-pull)  DO_PULL=0 ;;
        --yes)      ;;                  # (old option - starting is now automatic)
        --no-start) START=no; SHOW_LOG=no ;;
        --no-log)   SHOW_LOG=no ;;
        -h|--help)  sed -n '2,16p' "$0"; exit 0 ;;
        *)          echo "Unknown option: $arg (try --help)"; exit 1 ;;
    esac
done

# --- Steps (inside main so the whole file is read before step 1 can replace it) ---
main() {
    cd "$DIR" || fail "Can't open $DIR"
    [ "$(id -u)" -ne 0 ] || fail "Run without sudo:  bash update.sh"
    REBOOT_NEEDED=0

    step "1. Getting the latest files"
    if [ "$DO_PULL" -eq 0 ]; then
        note "Skipped (--no-pull)"
    elif [ ! -d .git ]; then
        note "Not a git folder - using the files already here"
    else
        before="$(git rev-parse HEAD)"
        git pull --ff-only || fail "git pull failed (if it mentions local changes, a file was edited on the Pi)"
        after="$(git rev-parse HEAD)"
        if [ "$before" = "$after" ]; then
            ok "Already up to date"
        else
            ok "Updated:"
            git diff --stat "$before" "$after" | sed 's/^/      /'
            if ! git diff --quiet "$before" "$after" -- update.sh; then
                note "update.sh changed - restarting it"
                exec bash "$DIR/update.sh" --no-pull "$@"
            fi
        fi
    fi

    step "2. Checking the files"
    [ -f "$MAIN" ] || fail "$MAIN is missing"
    [ -f rc.local ] || fail "rc.local is missing"
    # Stop here rather than install a boot file that points elsewhere
    grep -q "$MAIN" rc.local || fail "rc.local doesn't start $MAIN - fix rc.local in GitHub, then run this again"
    grep -q "cd $DIR " rc.local || fail "rc.local doesn't use this folder ($DIR) - fix rc.local in GitHub, then run this again"
    [ -x "$VENV_PYTHON" ] || fail "Pimoroni's Inky software isn't installed ($VENV_PYTHON not found).
    Install it (answer its questions), reboot, then run this again:
        git clone https://github.com/pimoroni/inky ~/inky
        cd ~/inky && ./install.sh
        sudo reboot"
    ok "$MAIN, rc.local and Pimoroni Python found"
    # Python packages the scripts need that aren't installed with the Inky library
    for pkg in qrcode; do
        if "$VENV_PYTHON" -c "import $pkg" 2> /dev/null; then
            ok "$pkg package installed"
        elif "$VENV_PYTHON" -m pip install --quiet "$pkg"; then
            ok "$pkg package installed (just now)"
        else
            warn "Couldn't install $pkg - the display works, but without that feature"
        fi
    done
    if [ -f birdfacts.json ]; then
        if "$VENV_PYTHON" -m json.tool birdfacts.json > /dev/null 2> /tmp/birdfacts_error; then
            ok "birdfacts.json is valid"
        else
            warn "birdfacts.json has a mistake (tiles will use Wikidata until fixed):"
            sed 's/^/      /' /tmp/birdfacts_error
        fi
    fi

    step "3. Setting up sound (birdsong, button D)"
    if [ ! -f birdsong.py ]; then
        note "birdsong.py not here - skipped"
    else
        # An audio player (BirdNET-Pi's ffmpeg usually provides ffplay)
        if "$VENV_PYTHON" birdsong.py --players | grep -q "none"; then
            note "No audio player - installing mpg123..."
            if sudo apt-get install -y -qq mpg123 > /dev/null; then
                ok "mpg123 installed"
            else
                warn "Couldn't install mpg123 - button D won't play sound"
            fi
        else
            ok "Audio player found"
        fi

        # The Pi's 3.5 mm headphone socket: switched on, volume set
        if grep -q "\[Headphones" "$SOUND_CARDS" 2> /dev/null; then
            ok "Headphone socket found"
            if [ -n "$HEADPHONE_VOLUME" ]; then
                if amixer -q -c Headphones sset PCM "$HEADPHONE_VOLUME" unmute 2> /dev/null; then
                    sudo alsactl store 2> /dev/null            # keep it after a reboot
                    ok "Headphone volume set to $HEADPHONE_VOLUME"
                else
                    warn "Couldn't set the headphone volume - try: alsamixer"
                fi
            fi
        else
            config=""
            for f in $CONFIG_FILES; do [ -f "$f" ] && { config="$f"; break; }; done
            if [ -z "$config" ]; then
                warn "Headphone socket not found (no config.txt to switch it on)"
            elif grep -q "^dtparam=audio=on" "$config"; then
                warn "Headphone socket not found although it's switched on - this Pi may not have one"
            else
                backup="$config.backup-$(date +%Y-%m-%d-%H%M)"
                sudo cp "$config" "$backup"
                if grep -q "^dtparam=audio=off" "$config"; then
                    sudo sed -i 's/^dtparam=audio=off/dtparam=audio=on/' "$config"
                else
                    printf '\n[all]\ndtparam=audio=on\n' | sudo tee -a "$config" > /dev/null
                fi
                REBOOT_NEEDED=1
                warn "Headphone socket was off - switched on in $config (old copy: $backup)"
            fi
        fi
        ok "Birdsong plays through: $("$VENV_PYTHON" birdsong.py --output)"
    fi

    step "4. Stopping the display"
    if pgrep -f "$RUNNING_PATTERN" > /dev/null; then
        sudo pkill -f "$RUNNING_PATTERN"
        for _ in $(seq "$STOP_TIMEOUT"); do
            pgrep -f "$RUNNING_PATTERN" > /dev/null || break
            sleep 1
        done
        pgrep -f "$RUNNING_PATTERN" > /dev/null && fail "Still running - try: sudo pkill -9 -f '$RUNNING_PATTERN'"
        ok "Stopped"
    else
        note "Wasn't running"
    fi

    step "5. Installing rc.local"
    if [ -f "$RC_TARGET" ] && cmp -s rc.local "$RC_TARGET"; then
        ok "Already up to date"
    else
        if [ -f "$RC_TARGET" ]; then
            backup="$RC_TARGET.backup-$(date +%Y-%m-%d-%H%M)"
            sudo cp "$RC_TARGET" "$backup" || fail "Couldn't back up $RC_TARGET"
            note "Old version saved as $backup"
        fi
        sudo install -m 755 -o root -g root rc.local "$RC_TARGET" || fail "Couldn't install $RC_TARGET"
        ok "Installed"
    fi

    step "6. Testing the database"
    "$VENV_PYTHON" -u "$MAIN" --check || fail "Database test failed"

    step "7. Demo: drawing the live screen (about 30 seconds)"
    "$VENV_PYTHON" -u "$MAIN" --once || fail "Drawing the screen failed"
    ok "Check the screen"

    step "8. Starting the display"
    if [ "$START" = yes ]; then
        # As rc.local does, without the wait. setsid + nohup: keeps running
        # after Ctrl+C below and after logging out of SSH.
        setsid nohup "$VENV_PYTHON" -u "$DIR/$MAIN" >> "$DIR/display.log" 2>&1 < /dev/null &
        sleep 3
        if pgrep -f "python3? .*$MAIN" > /dev/null; then
            ok "Running (it redraws once more in ~30 s)"
        else
            warn "It stopped - see: tail -n 30 $DIR/display.log"
            SHOW_LOG=no
        fi
    else
        note "Not started - it starts at the next boot"
    fi

    echo
    if [ "$REBOOT_NEEDED" -eq 1 ]; then
        echo "Update finished - reboot to switch on the headphone socket:  sudo reboot"
    else
        echo "Update finished."
    fi

    if [ "$SHOW_LOG" = yes ]; then
        echo
        echo "Showing the live log - press Ctrl+C to stop watching (the display keeps running)."
        echo
        exec tail -n 15 -f "$DIR/display.log"
    fi
}

main "$@"
exit
