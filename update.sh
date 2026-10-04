#!/bin/bash
# =============================================================================
# update.sh - install the latest BirdNET-Pi display from GitHub
#
# Steps: 1 git pull   2 check files (and install missing Python packages)
#        3 stop the display   4 install rc.local
#        (if changed; old one backed up in /etc)   5 database test
#        6 demo (--once)   7 start the display (asks first)
#
# Run from this folder, without sudo:
#   bash update.sh              full update
#   bash update.sh --no-pull    use the files already here
#   bash update.sh --yes        start at the end without asking
#   bash update.sh --no-start   don't start at the end
# =============================================================================

# --- Settings ---
MAIN="bbbb-display.py"
VENV_PYTHON="/home/pi/.virtualenvs/pimoroni/bin/python3"
RC_TARGET="/etc/rc.local"
STOP_TIMEOUT=15
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
START=ask
for arg in "$@"; do
    case "$arg" in
        --no-pull)  DO_PULL=0 ;;
        --yes)      START=yes ;;
        --no-start) START=no ;;
        -h|--help)  sed -n '2,15p' "$0"; exit 0 ;;
        *)          echo "Unknown option: $arg (try --help)"; exit 1 ;;
    esac
done

# --- Steps (inside main so the whole file is read before step 1 can replace it) ---
main() {
    cd "$DIR" || fail "Can't open $DIR"
    [ "$(id -u)" -ne 0 ] || fail "Run without sudo:  bash update.sh"

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
    [ -x "$VENV_PYTHON" ] || fail "Pimoroni Python not found at $VENV_PYTHON"
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

    step "3. Stopping the display"
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

    step "4. Installing rc.local"
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

    step "5. Testing the database"
    "$VENV_PYTHON" -u "$MAIN" --check || fail "Database test failed"

    step "6. Demo: drawing the live screen (about 30 seconds)"
    "$VENV_PYTHON" -u "$MAIN" --once || fail "Drawing the screen failed"
    ok "Check the screen"

    step "7. Starting the display"
    if [ "$START" = ask ]; then
        read -r -p "  Start it now in the background? [Y/n] " reply
        case "$reply" in [nN]*) START=no ;; *) START=yes ;; esac
    fi
    if [ "$START" = yes ]; then
        # As rc.local does, without the wait; nohup keeps it running after logout
        nohup "$VENV_PYTHON" -u "$DIR/$MAIN" >> "$DIR/display.log" 2>&1 &
        sleep 3
        if pgrep -f "python3? .*$MAIN" > /dev/null; then
            ok "Running (it redraws once more in ~30 s). Log: tail -f $DIR/display.log"
        else
            warn "It stopped - see: tail -n 30 $DIR/display.log"
        fi
    else
        note "Not started - it starts at the next boot"
    fi

    echo; echo "Update finished."
}

main "$@"
exit
