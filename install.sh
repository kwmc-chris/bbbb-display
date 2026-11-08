#!/bin/bash
# First-time setup on a new Raspberry Pi. Run once, without sudo: bash install.sh
# After this, update.sh keeps it up to date.

SERVICE=bbbb-display
UPDATE_TIME="0 3 * * *"          # nightly update at 3am (minute hour * * *)

cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
[ "$(id -u)" -ne 0 ] || { echo "Run without sudo: bash install.sh"; exit 1; }

# System packages
sudo apt-get update -qq &&
sudo apt-get install -y -qq python3-venv python3-dev build-essential python3-numpy python3-pil \
    fonts-dejavu-core fonts-dejavu-extra ffmpeg alsa-utils || exit 1

# Screen connection: SPI, I2C and the Inky's spi0-0cs setting
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
printf '[all]\ndtoverlay=spi0-0cs\n' | sudo tee -a /boot/firmware/config.txt > /dev/null

# Python packages
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet -r requirements.txt || exit 1

# Settings (an existing settings.toml is kept)
[ -f settings.toml ] || cp settings.example.toml settings.toml

# Start at boot
sudo tee /etc/systemd/system/$SERVICE.service > /dev/null << EOF
[Unit]
Description=Bird display
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$DIR
ExecStartPre=/bin/sh -c 'test \$\$(cut -d. -f1 /proc/uptime) -gt 120 || sleep 45'
ExecStart=$DIR/.venv/bin/python -u $DIR/start.py
Restart=on-failure
RestartSec=60
StandardOutput=append:$DIR/display.log
StandardError=append:$DIR/display.log

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --quiet $SERVICE

# Nightly update
echo "$UPDATE_TIME $(id -un) bash $DIR/update.sh" | sudo tee /etc/cron.d/$SERVICE > /dev/null
sudo chmod 644 /etc/cron.d/$SERVICE

echo "Done. Choose the display in settings.toml (nano settings.toml), then: sudo reboot"
