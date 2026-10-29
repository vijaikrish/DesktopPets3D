#!/usr/bin/env bash
# Double-click in Finder to start DesktopPets3D from source (macOS). First time: right-click > Open.
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || bash ./setup.sh
bash ./run.sh
