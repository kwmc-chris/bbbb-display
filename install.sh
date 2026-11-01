#!/bin/bash
# Sets up the bird display on this Pi, or brings it up to date. Run from this
# folder, without sudo:
#     bash install.sh            (--no-log: don't show the log at the end)
# Safe to run again at any time. update.sh runs it after each nightly update.

SERVICE=bbbb-display
UPDATE_TIME="0 3 * * *"          # nightly update at 3am (cron format: minute hour * * *)

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
[ "$(id -u)" -ne 0 ] || { echo "Run without sudo:  bash install.sh"; exit 1; }
USER_NAME="$(id -un)"
REBOOT=0

echo "== System packages"
PKGS="git cron python3-venv python3-dev build-essential python3-numpy python3-pil
      fonts-dejavu-core fonts-dejavu-extra ffmpeg alsa-utils"
sudo apt-get install -y -qq $PKGS > /dev/null 2>&1 ||
    { sudo apt-get update -qq && sudo apt-get install -y -qq $PKGS > /dev/null; } ||
    { echo "Couldn't install the system packages - check the internet connection"; exit 1; }
python3 -c 'import tomllib' 2> /dev/null ||
    { echo "Python 3.11 or newer is needed (Raspberry Pi OS Bookworm or later)"; exit 1; }

echo "== Screen connection (SPI, I2C)"
for i in spi i2c; do
    if [ "$(sudo raspi-config nonint get_$i)" != "0" ]; then        # 0 = already on
        sudo raspi-config nonint do_$i 0 && REBOOT=1
    fi
done
CONFIG=/boot/firmware/config.txt
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt
if ! grep -q "^dtoverlay=spi0-0cs" "$CONFIG"; then                  # the Inky needs this
    sudo cp "$CONFIG" "$CONFIG.backup"
    printf '\n[all]\ndtoverlay=spi0-0cs\n' | sudo tee -a "$CONFIG" > /dev/null
    REBOOT=1
fi

echo "== Sound (headphone socket on, full volume)"
if grep -q "\[Headphones" /proc/asound/cards 2> /dev/null; then
    amixer -q -c Headphones sset PCM 100% unmute 2> /dev/null && sudo alsactl store 2> /dev/null
elif ! grep -q "^dtparam=audio=on" "$CONFIG"; then
    sudo sed -i '/^dtparam=audio=off/d' "$CONFIG"
    printf '\n[all]\ndtparam=audio=on\n' | sudo tee -a "$CONFIG" > /dev/null
    REBOOT=1
fi

echo "== Python packages (.venv)"
[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv || exit 1
.venv/bin/pip install --quiet -r requirements.txt || exit 1

echo "== Settings"
if [ -f settings.toml ]; then
    echo "settings.toml kept as it is"
else
    cp settings.example.toml settings.toml
    echo "Made settings.toml - edit it to choose the display:  nano settings.toml"
fi
.venv/bin/python -c 'import tomllib; tomllib.load(open("settings.toml", "rb"))' ||
    { echo "settings.toml has a mistake (see above) - fix it, then run this again"; exit 1; }

echo "== Start at boot, update nightly"
sudo tee /etc/systemd/system/$SERVICE.service > /dev/null << EOF
[Unit]
Description=Bird display
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$DIR
# Just after booting, give BirdNET-Pi and the network time to start
ExecStartPre=/bin/sh -c 'test \$\$(cut -d. -f1 /proc/uptime) -gt 120 || sleep 45'
ExecStart=$DIR/.venv/bin/python -u $DIR/start.py
Restart=on-failure
RestartSec=60
StandardOutput=append:$DIR/display.log
StandardError=append:$DIR/display.log

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --quiet $SERVICE
echo "$UPDATE_TIME $USER_NAME bash $DIR/update.sh" | sudo tee /etc/cron.d/$SERVICE > /dev/null
sudo chmod 644 /etc/cron.d/$SERVICE                 # cron ignores it otherwise

if [ $REBOOT -eq 1 ]; then
    echo "Done - now reboot (sudo reboot). The display starts by itself after that."
    exit 0
fi
touch display.log
sudo systemctl restart $SERVICE
echo "Done - the display is running (first picture in about 30 seconds)."
[ "$1" = "--no-log" ] && exit 0
echo "Showing the log - Ctrl+C stops watching, the display keeps running."
exec tail -n 15 -f display.log
