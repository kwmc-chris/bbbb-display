#!/bin/bash
# Nightly update from GitHub, run by cron at 3am.
# Off: nightly_update = false in settings.toml
# By hand: bash update.sh --now

main() {
    # Go to this folder; at night, write output to update.log
    cd "$(dirname "$0")" || exit 1
    [ -t 1 ] || exec >> update.log 2>&1
    echo "$(date '+%Y-%m-%d %H:%M:%S')  Update"

    # Trim logs over 5000 lines to the last 2000
    for f in update.log display.log; do
        if [ -f $f ] && [ "$(wc -l < $f)" -gt 5000 ]; then
            tail -n 2000 $f > $f.tmp && cat $f.tmp > $f && rm $f.tmp
        fi
    done

    # Stop if nightly updates are off (skipped with --now)
    if [ "$1" != "--now" ]; then
        on=$(python3 -c 'import tomllib; print(tomllib.load(open("settings.toml", "rb")).get("nightly_update", True))')
        if [ "$on" = "False" ]; then
            echo "Nightly updates are off in settings.toml"
            exit 0
        fi
    fi

    # Get the latest version
    before=$(git rev-parse HEAD)
    if ! git pull --ff-only -q; then
        echo "git pull failed. If it mentions local changes, a file was edited on this Pi."
        exit 1
    fi

    # Stop if nothing changed
    if [ "$(git rev-parse HEAD)" = "$before" ]; then
        echo "Already up to date"
        exit 0
    fi

    # List the changes, update Python packages, restart the display
    git log --oneline "$before..HEAD"
    .venv/bin/pip install --quiet -r requirements.txt
    sudo systemctl restart bbbb-display
}

main "$@"
exit
