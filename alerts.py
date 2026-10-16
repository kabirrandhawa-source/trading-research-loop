"""Alerts for the trading loop: a macOS notification always, plus a phone push via ntfy
(https://ntfy.sh) when NTFY_TOPIC is set in config/.env, plus an iMessage text from this Mac's Messages
app for high and urgent alerts when SMS_TO (a phone number, e.g. +15551234567) is set in config/.env.

Alerts never raise. A failed alert must not stop trading or hide the original problem;
failures are written to the journal instead.

    python alerts.py test        # send a test alert through every channel (no text: priority default)
    python alerts.py test-text   # send one test iMessage to SMS_TO
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
REPEAT_WINDOW_S = 1800          # the same title goes out at most once per 30 minutes (urgent excepted)
STATE_PATH = ROOT / "memory" / "alert_state.json"

_OSA = """on run argv
display notification (item 2 of argv) with title (item 1 of argv)
end run"""

_IMESSAGE = """on run argv
tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send (item 2 of argv) to participant (item 1 of argv) of svc
end tell
end run"""
TEXT_PRIORITIES = ("high", "urgent")    # only these become texts; the rest stay pushes


def _mac(title, message):
    if sys.platform != "darwin":
        return "skipped (not macOS)"
    r = subprocess.run(["osascript", "-e", _OSA, title, message[:250]],
                       capture_output=True, text=True, timeout=10)
    return "ok" if r.returncode == 0 else f"error: {r.stderr.strip()[:200]}"


def _imessage(title, message, priority):
    to = os.getenv("SMS_TO", "").strip()
    if not to:
        return "skipped (SMS_TO not set)"
    if priority not in TEXT_PRIORITIES:
        return "skipped (priority below high)"
    if sys.platform != "darwin":
        return "skipped (not macOS)"
    text = f"Trading desk: {title}\n{message}"[:600]
    r = subprocess.run(["osascript", "-e", _IMESSAGE, to, text], capture_output=True, text=True, timeout=20)
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


def _recently_sent(title, now, state_path=None):
    """True if this title was sent within REPEAT_WINDOW_S; records the send otherwise."""
    import json
    path = Path(state_path or STATE_PATH)
    try:
        state = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        state = {}
    if now - state.get(title, 0) < REPEAT_WINDOW_S:
        return True
    state = {k: v for k, v in state.items() if now - v < 86400}
    state[title] = now
    try:
        path.write_text(json.dumps(state))
    except Exception:
        pass
    return False


def send(title, message, priority="default", tags=(), journal_dir=None, state_path=None):
    """Send an alert on every configured channel. Returns {channel: result}.
    Repeats of the same title within 30 minutes are journaled but not sent, unless urgent."""
    import time
    if priority != "urgent" and _recently_sent(title, time.time(), state_path):
        entry = {"event": "alert_suppressed", "title": title, "priority": priority}
        try:
            journal.log(entry, journal_dir)
        except Exception:
            pass
        return {"suppressed": "repeat within 30 minutes"}
    results = {}
    for name, fn in (("mac", lambda: _mac(title, message)),
                     ("ntfy", lambda: _ntfy(title, message, priority, tags)),
                     ("text", lambda: _imessage(title, message, priority))):
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = f"error: {type(e).__name__}: {e}"[:200]
    entry = {"event": "alert", "title": title, "priority": priority, "channels": results}
    try:
        journal.log(entry, journal_dir)
    except Exception:
        pass
    return results


if __name__ == "__main__":
    if sys.argv[1:] == ["test-text"]:
        print({"text": _imessage("test text", "If you got this, high and urgent alerts will text you.", "high")})
    elif sys.argv[1:] == ["test"]:
        print(send("Trading loop: test alert", "If you can read this, alerts work.", "default",
                   ["white_check_mark"]))
    else:
        print(__doc__)
