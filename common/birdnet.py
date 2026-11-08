"""BirdNET-Pi's database of detections (read-only) and its settings file."""

import os
import sqlite3

DATABASE = os.path.expanduser("~/BirdNET-Pi/scripts/birds.db")
CONF_FILES = ["/etc/birdnet/birdnet.conf", os.path.expanduser("~/BirdNET-Pi/birdnet.conf")]


def query(sql, *params):
    """Rows from the database; each row works like a dict."""
    if not os.path.exists(DATABASE):
        raise FileNotFoundError(f"BirdNET-Pi's database isn't at {DATABASE}")
    con = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def latest():
    """The most recent detection, or None."""
    rows = query("SELECT * FROM detections ORDER BY Date DESC, Time DESC LIMIT 1")
    return rows[0] if rows else None


def sci_name(com_name):
    """Scientific name of a bird in the database, or None."""
    try:
        rows = query("SELECT Sci_Name FROM detections WHERE Com_Name = ? LIMIT 1", com_name)
    except (OSError, sqlite3.Error):
        return None
    return rows[0]["Sci_Name"] if rows else None


def config():
    """BirdNET-Pi's settings (birdnet.conf) as a dict, or {}."""
    for path in CONF_FILES:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        conf = {}
        for line in lines:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                conf[key.strip()] = value.strip().strip('"').strip("'")
        return conf
    return {}
