# Third-party software and assets

DesktopPets3D uses the following. The ready-made apps (Windows / macOS releases) **include** the libraries marked
"bundled".

| Component | Version used | Licence | Where | Notes |
|---|---|---|---|---|
| **Qt for Python (PySide6)** and **Qt 6** incl. **Qt WebEngine** (Chromium) | PySide6 6.12 | LGPL v3 (also GPL v2/v3, commercial) | bundled in `_internal/PySide6` (Windows) / the `.app` | See "Qt and the LGPL" below |
| **Three.js** | r186 | MIT | `web/vendor/three/` (with its `LICENSE`) | 3D rendering in the pet window |
| **NumPy** | 2.x | BSD-3-Clause (+ bundled parts under 0BSD, MIT, Zlib, CC0) | bundled | The conure's emotion engine |
| **Python** | 3.12 (releases) | PSF License | bundled | |
| **PyInstaller** bootloader | 6.x | GPL v2 with the bootloader exception | the `.exe` / app launcher | The exception allows distributing the built app under any licence |
| **Freesound** recordings | - | CC0 1.0; two files CC BY 3.0 / 4.0 | `pets/sun_conure/sounds/` | Credits: `pets/sun_conure/sounds/CREDITS.md` |

## Qt and the LGPL

The apps link the Qt and PySide6 libraries dynamically and ship them unmodified as separate files. You may replace
them with your own builds of the same versions: on Windows they are the `Qt6*.dll` files and `PySide6/*.pyd` in
`_internal/PySide6`; on macOS the Qt frameworks inside `DesktopPets3D.app/Contents/Frameworks`.

- Qt source code: <https://download.qt.io/official_releases/qt/> and <https://code.qt.io>
- PySide6 source code: <https://code.qt.io/cgit/pyside/pyside-setup.git>
- Licence texts: `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` (the LGPL v3 adds permissions to the GPL v3).

Qt WebEngine contains Chromium and its third-party components, which carry their own (mostly BSD-style) licences. The
list is in the Qt documentation: <https://doc.qt.io/qt-6/qtwebengine-licensing.html>.
