"""Alerts for the trading loop: a macOS notification always, plus a phone push via ntfy
(https://ntfy.sh) when NTFY_TOPIC is set in config/.env.

Alerts never raise. A failed alert must not stop trading or hide the original problem;
failures are written to the journal instead.

    python alerts.py test     # send a test alert through every channel
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

import journal

ROOT = Path(__file__).parent
load_dotenv(ROOT / "config" / ".env")

PRIORITIES = {"low": "2", "default": "3", "high": "4", "urgent": "5"}

_OSA = """on run argv
display notification (item 2 of argv) with title (item 1 of argv)
end run"""


def _mac(title, message):
    if sys.platform != "darwin":
        return "skipped (not macOS)"
    r = subprocess.run(["osascript", "-e", _OSA, title, message[:250]],
                       capture_output=True, text=True, timeout=10)
    return "ok" if r.returncode == 0 else f"error: {r.stderr.strip()[:200]}"


def _ntfy(title, message, priority, tags):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        return "skipped (NTFY_TOPIC not set)"
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    req = urllib.request.Request(
        f"{server}/{topic}", data=message.encode(), method="POST",
        headers={"Title": title.encode("ascii", "replace").decode(),
                 "Priority": PRIORITIES.get(priority, "3"), "Tags": ",".join(tags)})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return "ok" if resp.status == 200 else f"http {resp.status}"


def send(title, message, priority="default", tags=(), journal_dir=None):
    """Send an alert on every configured channel. Returns {channel: result}."""
    results = {}
    for name, fn in (("mac", lambda: _mac(title, message)),
                     ("ntfy", lambda: _ntfy(title, message, priority, tags))):
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = f"error: {type(e).__name__}: {e}"[:200]
    entry = {"event": "alert", "title": title, "priority": priority, "channels": results}
    try:
        journal.log(entry, journal_dir) if journal_dir else journal.log(entry)
    except Exception:
        pass
    return results


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        print(send("Trading loop: test alert", "If you can read this, alerts work.", "default",
                   ["white_check_mark"]))
    else:
        print(__doc__)
