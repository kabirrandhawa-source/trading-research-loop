"""Compress finished days of recorded data (data/pm/stream-*.db, live-*.db) with xz, about 6x smaller.

A file is archived only when its day (or month, for older monthly files) is over in UTC and it has
not been written to for 30 minutes. The .xz file is verified before the original is deleted.
Run nightly by launchd; safe to run by hand any time:

    python -m pm.archive            # compress finished files
    python -m pm.archive --restore data/pm/stream-2026-10-13.db.xz   # decompress one for analysis
"""
import argparse
import lzma
import re
import shutil
import sqlite3
import time
from pathlib import Path

from pm import store

NAME = re.compile(r"^(stream|live)-(\d{4}-\d{2})(-\d{2})?\.db$")
QUIET_S = 1800
CHUNK = 8 * 1024 * 1024


def finished(path, now=None):
    m = NAME.match(path.name)
    if not m:
        return False
    now = now or time.time()
    period = m.group(2) + (m.group(3) or "")
    current = time.strftime("%Y-%m-%d" if m.group(3) else "%Y-%m", time.gmtime(now))
    return period < current and now - path.stat().st_mtime > QUIET_S


def compress(path):
    """Checkpoint, xz-compress, verify, then delete the original. Returns (raw_bytes, xz_bytes)."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    out = path.with_name(path.name + ".xz")
    tmp = out.with_name(out.name + ".part")
    with open(path, "rb") as src, lzma.open(tmp, "wb", preset=6) as dst:
        shutil.copyfileobj(src, dst, CHUNK)
    with lzma.open(tmp, "rb") as check, open(path, "rb") as src:     # verify byte-for-byte
        while True:
            a, b = src.read(CHUNK), check.read(CHUNK)
            if a != b:
                tmp.unlink()
                raise RuntimeError(f"verification failed for {path.name}; original kept")
            if not a:
                break
    tmp.rename(out)
    raw = path.stat().st_size
    for extra in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        extra.unlink(missing_ok=True)
    return raw, out.stat().st_size


def restore(xz_path, dest_dir=None):
    xz_path = Path(xz_path)
    dest = Path(dest_dir or xz_path.parent) / xz_path.name[:-3]
    with lzma.open(xz_path, "rb") as src, open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst, CHUNK)
    return dest


def run(data_dir=None):
    d = Path(data_dir or store.DATA)
    done = []
    for path in sorted(d.glob("*.db")):
        if finished(path):
            raw, xz = compress(path)
            done.append((path.name, raw, xz))
            print(f"{path.name}: {raw / 1e6:.0f} MB -> {xz / 1e6:.1f} MB", flush=True)
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--restore")
    a = p.parse_args()
    print(restore(a.restore) if a.restore else f"{len(run())} file(s) archived")
