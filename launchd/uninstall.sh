#!/bin/bash
# Stop and remove every launchd job in this folder.
DIR="$(cd "$(dirname "$0")" && pwd)"
for SRC in "$DIR"/*.plist; do
  LABEL="$(basename "$SRC" .plist)"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Stopped $LABEL" || echo "$LABEL was not loaded"
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
done
