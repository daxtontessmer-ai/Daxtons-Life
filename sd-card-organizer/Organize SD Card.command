#!/bin/bash
# Double-click this file on the MacBook to open the SD card organizer.
cd "$(dirname "$0")" || exit 1
URL="http://127.0.0.1:8765/"

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display dialog "This Mac needs Python 3, which comes with Apple’s command line tools.

Click Install in the next window, wait until it finishes, then double-click Organize SD Card.command again." buttons {"OK"} default button 1 with title "Organize SD card"'
  xcode-select --install >/dev/null 2>&1
  exit 1
fi

if curl -fsS --max-time 1 "${URL}api/health" >/dev/null 2>&1; then
  open "$URL"
  echo "The organizer is already running. It was opened in the browser."
  echo "Leave that window open while you copy."
  exit 0
fi

(sleep 0.8 && open "$URL") &
exec python3 server.py
