# Building the stand-alone apps

The apps are built with [PyInstaller](https://pyinstaller.org). It bundles Python, Qt (with its Chromium-based web
engine), numpy, the viewer (`web/`) and the pets (`pets/`) into one folder (Windows) or one `.app` (macOS).
**PyInstaller cannot cross-compile:** build the Windows app on Windows and the macOS app on a Mac. The GitHub
workflow below does both for you on GitHub's machines.

## Automatic builds on GitHub (recommended)

`.github/workflows/build.yml` runs on GitHub Actions:

1. on **Windows** (x64) and **macOS 14** (Apple silicon), with Python 3.12;
2. installs `requirements-build.txt`, runs the **24 unit tests** and `app.plugin_check`;
3. builds with `packaging/DesktopPets3D.spec`;
4. zips the result: `DesktopPets3D-windows-x64.zip`, `DesktopPets3D-macos-arm64.zip`.

When it runs:
- **On a version tag** (`v0.4.0`, `v0.5.0`, ...): the zips are attached to that GitHub Release automatically.
- **On demand:** GitHub > your repository > **Actions** > **build** > **Run workflow**. The zips are then under that
  run's **Artifacts** (kept 90 days).

How to tag a release: [PUBLISHING.md](PUBLISHING.md).

## Building on your own machine

### Windows

```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\DesktopPets3D.spec
dist\DesktopPets3D\DesktopPets3D.exe --selftest
```

- Output: `dist\DesktopPets3D\` (`DesktopPets3D.exe` + `_internal\`, about 535 MB). Zip the whole folder to share it.
- **Always run the built exe with `--selftest`** before sharing: it opens the real window, loads the model and exits
  with code 0 only if everything worked (it prints `SELFTEST OK ...`). A finished PyInstaller run alone proves nothing.
- If the project lives in a OneDrive / Dropbox folder, build outside it (cloud sync locks files mid-build):
  `... -m PyInstaller --distpath C:\Temp\dp3d\dist --workpath C:\Temp\dp3d\work packaging\DesktopPets3D.spec`

### macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/DesktopPets3D.spec
dist/DesktopPets3D.app/Contents/MacOS/DesktopPets3D --selftest
ditto -c -k --sequesterRsrc --keepParent dist/DesktopPets3D.app DesktopPets3D-macos-arm64.zip
```

- Output: `dist/DesktopPets3D.app`. Built on an Apple-silicon Mac it runs on Apple silicon; built on an Intel Mac it
  runs on Intel Macs.
- `LSUIElement` is set in the app's Info.plist: no Dock icon, as befits a desktop companion.
- PyInstaller signs the app ad hoc. To give it to other people without the Gatekeeper warning you need an Apple
  Developer ID: sign with `codesign --deep --options runtime --sign "Developer ID Application: ..."` and notarise with
  `xcrun notarytool`. Without that, users follow the "right-click > Open" / `xattr` steps in [INSTALL.md](INSTALL.md).

## What the recipe does (`packaging/DesktopPets3D.spec`)

- Entry point `packaging/launch.py` (= `python -m app.desktop`).
- `web/` and `pets/` are copied as data, without `__pycache__`. Pet engines are plain `.py` files loaded at run time,
  so their imports are listed in `hiddenimports` (numpy and a few standard modules). **A new pet whose engine imports
  another library must be added there.**
- Removes what a QtWebEngine widget app never loads (~110 MB): QML modules, Qt Quick 3D / Controls libraries, and
  Qt's UI translations (Chromium keeps its `en-US` locale).
- Icons: `packaging/make_icons.py` makes `.ico` and `.icns` from `pets/sun_conure/icon.png` (needs Pillow; without
  it the build uses the default icon).
- Windows: `console=False` (no console window). macOS: `BUNDLE` with bundle id `io.github.desktoppets3d`.

## Versions

The version shown in the tray tooltip and the log comes from `app/__init__.py` (`__version__`). Update it, update
`CHANGELOG.md`, then tag the same version (`v0.4.0`).
