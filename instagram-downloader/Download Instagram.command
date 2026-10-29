#!/bin/bash
# Opens the Instagram downloader. Leave the Terminal window open until you are done.
set -euo pipefail

cd "$(dirname "$0")" || exit 1
export PATH="$HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export YTDLP_NO_PLUGINS=1
URL="http://127.0.0.1:8766/"

note() {
  echo "$1"
  if ! command -v osascript >/dev/null 2>&1; then
    return 0
  fi
  local escaped
  escaped=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')
  osascript -e "display dialog \"$escaped\" buttons {\"OK\"} default button 1 with title \"Instagram\"" >/dev/null 2>&1 || true
}

if [ ! -x .venv/bin/python ]; then
  note "Double-click Install Instagram Downloader.command first. It only has to run once."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg was not found on the PATH. Some videos need it to finish. It should live in ~/bin."
fi

if .venv/bin/python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8766/api/health", timeout=1).read()' >/dev/null 2>&1; then
  if command -v open >/dev/null 2>&1; then
    open "$URL"
  fi
  echo "The downloader is already running. It was opened in the browser."
  echo "Leave that window open while you download."
  exit 0
fi

if command -v open >/dev/null 2>&1; then
  (sleep 0.8 && open "$URL") &
fi
exec .venv/bin/python server.py
