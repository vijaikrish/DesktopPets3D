#!/usr/bin/env bash
# DesktopPets3D - start from source on macOS / Linux (run ./setup.sh once first).
#   ./run.sh            start in the background (quit from the bird's right-click menu or the menu-bar icon)
#   ./run.sh --debug    stay in the terminal and show errors
cd "$(dirname "$0")"
unset PYTHONPATH PYTHONHOME
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
if [ "${1:-}" = "--debug" ]; then
  shift
  exec "$PY" -m app.desktop "$@"
fi
nohup "$PY" -m app.desktop "$@" >/dev/null 2>&1 &
echo "DesktopPets3D started (log: ~/Library/Application Support/DesktopPets3D/logs on macOS, ~/.local/share/DesktopPets3D/logs on Linux)"
