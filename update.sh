#!/bin/bash
# Gets the latest version from GitHub and installs it. Runs every night at 3am
# (set in install.sh) unless settings.toml has  nightly_update = false.
# Run it by hand any time with:  bash update.sh --now
# At night it writes to update.log.

main() {
    cd "$(dirname "$0")" || exit 1
    [ -t 1 ] || exec >> update.log 2>&1            # not run by hand: write to the log
    echo "$(date '+%Y-%m-%d %H:%M:%S')  Update"

    for f in update.log display.log; do            # keep the logs from growing forever
        if [ -f $f ] && [ "$(wc -l < $f)" -gt 5000 ]; then
            tail -n 2000 $f > $f.tmp && cat $f.tmp > $f && rm $f.tmp
        fi
    done

    if [ "$1" != "--now" ]; then
        on=$(python3 -c 'import tomllib; print(tomllib.load(open("settings.toml", "rb")).get("nightly_update", True))')
        if [ "$on" = "False" ]; then
            echo "Nightly updates are off in settings.toml"
            exit 0
        fi
    fi

    before=$(git rev-parse HEAD)
    if ! git pull --ff-only -q; then
        echo "git pull failed. If it mentions local changes, a file was edited on this Pi:"
        echo "  git status        shows which;   git checkout <file>   undoes the edit"
        exit 1
    fi
    if [ "$(git rev-parse HEAD)" = "$before" ]; then
        echo "Already up to date"
        exit 0
    fi
    git log --oneline "$before..HEAD"
    bash install.sh --no-log
}

main "$@"     # (all in main, so a new copy of this file arriving with git pull is safe)
exit
