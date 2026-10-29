#!/bin/bash
# First-time setup. Copies this folder to ~/Applications and installs the pinned Python packages.
# No Homebrew and no sudo. Needs Python 3.12 on PATH (Daxton's copy is in ~/bin).
set -euo pipefail

export PATH="$HOME/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if [ "$(id -u)" -eq 0 ]; then
  echo "Don't run this with sudo."
  exit 1
fi

note() {
  echo "$1"
  if ! command -v osascript >/dev/null 2>&1; then
    return 0
  fi
  local escaped
  escaped=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')
  osascript -e "display dialog \"$escaped\" buttons {\"OK\"} default button 1 with title \"Instagram\"" >/dev/null 2>&1 || true
}

if ! command -v python3 >/dev/null 2>&1; then
  note "Python 3.12 was not found. It should be on the PATH, in ~/bin."
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
  note "This needs Python 3.12, because the pinned packages are for that version. python3 is $(python3 --version 2>&1)."
  exit 1
fi

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Applications/instagram-downloader"
mkdir -p "$HOME/Applications"

if [ "$SRC" != "$DEST" ]; then
  mkdir -p "$DEST"
  tar -C "$SRC" \
    --exclude .venv \
    --exclude __pycache__ \
    --exclude .partial \
    -cf - . | tar -C "$DEST" -xf -
fi

cd "$DEST"
python3 -m venv .venv
PIP_DISABLE_PIP_VERSION_CHECK=1 .venv/bin/python -m pip install \
  --disable-pip-version-check \
  --require-hashes \
  --only-binary=:all: \
  -r requirements.txt
chmod +x "$DEST/Install Instagram Downloader.command" "$DEST/Download Instagram.command"

echo ""
echo "Installed in $DEST"
echo "Next, double-click Download Instagram.command"
echo "The packages came from pypi.org and files.pythonhosted.org. Nothing else was installed."
