#!/usr/bin/env bash
# DesktopPets3D - one-time setup on macOS / Linux: a private Python environment (.venv) with PySide6 + numpy.
# Needs Python 3.10 or newer (macOS: https://www.python.org/downloads/macos/ or `brew install python`).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ needed, found " + sys.version.split()[0]'
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo
echo "Done. Start the bird with:  ./run.sh   (or double-click run_mac.command in Finder)"
