#!/bin/bash
# First-time setup on a new Pi. Run without sudo: bash install.sh

# set working folder and check normal user, not sudo
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
[ "$(id -u)" -ne 0 ] || { echo "Run without sudo: bash install.sh"; exit 1; }

# install system packages
sudo apt-get update -qq &&
sudo apt-get install -y -qq python3-venv python3-dev build-essential python3-numpy python3-pil \
    fonts-dejavu-core fonts-dejavu-extra ffmpeg alsa-utils || exit 1

# Screen connections - SPI, I2C and special Inky setting
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
printf '[all]\ndtoverlay=spi0-0cs\n' | sudo tee -a /boot/firmware/config.txt > /dev/null

# install python packages
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet -r requirements.txt || exit 1

# Check no existing and copy settings file
[ -f settings.toml ] || cp settings.example.toml settings.toml

# Start at boot
sudo tee /etc/systemd/system/bbbb-display.service > /dev/null << EOF
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
sudo systemctl enable --quiet bbbb-display

# Nightly update at 3am (minute hour x x x)
echo "0 3 * * * $(id -un) bash $DIR/update.sh" | sudo tee /etc/cron.d/bbbb-display > /dev/null
sudo chmod 644 /etc/cron.d/bbbb-display

echo "Done. Choose the display in settings.toml (nano settings.toml), then: sudo reboot"