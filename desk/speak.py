"""Speak a short answer aloud on this Mac (macOS `say`). Strips markdown; long text is cut.

    .venv/bin/python -m desk.speak "BTC lag test failed. Nothing needs your decision today."

Voice: DESK_VOICE in config/.env (default Samantha). Better voices: System Settings > Accessibility >
Spoken Content > System voice > Manage Voices (e.g. download an Enhanced or Premium English voice),
then set DESK_VOICE to its name.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")
MAX_CHARS = 700


def clean(text):
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)              # code
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)      # links -> link text
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>|]", "", text)                        # markdown symbols
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(".", 1)[0] + "."
    return text


def speak(text, voice=None):
    voice = voice or os.getenv("DESK_VOICE", "Samantha")
    t = clean(text)
    if t:
        subprocess.run(["say", "-v", voice, "-r", "185", t], check=False)
    return t


if __name__ == "__main__":
    print(speak(" ".join(sys.argv[1:]) or sys.stdin.read()))
