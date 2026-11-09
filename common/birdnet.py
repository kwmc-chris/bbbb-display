"""BirdNET-Pi's database of detections (read-only)."""

import os
import sqlite3

DATABASE = os.path.expanduser("~/BirdNET-Pi/scripts/birds.db")


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
