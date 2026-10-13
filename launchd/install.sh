#!/bin/bash
# Install (or reinstall) every launchd job in this folder for the current user.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/../logs"
for SRC in "$DIR"/*.plist; do
  LABEL="$(basename "$SRC" .plist)"
  DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  for _ in $(seq 1 20); do                           # wait until macOS has fully unloaded it
    launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || break
    sleep 0.5
  done
  cp "$SRC" "$DEST"
  launchctl bootstrap "gui/$(id -u)" "$DEST"
  echo "Installed $LABEL"
done
