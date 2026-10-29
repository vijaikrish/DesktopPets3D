# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Windows and macOS (run it ON the target OS - PyInstaller does not cross-compile):
#     python -m PyInstaller --noconfirm --clean packaging/DesktopPets3D.spec
# Windows -> dist/DesktopPets3D/DesktopPets3D.exe (+ _internal/)     macOS -> dist/DesktopPets3D.app
# The pet plugins (pets/) and the web viewer (web/) are shipped as data: plugin engines are loaded from their .py
# files at runtime, so their imports (numpy) are listed as hidden imports.
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'packaging'))
from app import APP_NAME, __version__   # noqa: E402

try:
    from make_icons import make as _make_icons
    ICO, ICNS = _make_icons()
except Exception as e:                       # Pillow missing: build without a custom icon
    print('icons skipped:', e)
    ICO = ICNS = None

EXCL = ['__pycache__', '*.pyc', '_probe_data', '.DS_Store']
datas = [Tree(os.path.join(ROOT, 'web'), prefix='web', excludes=EXCL),
         Tree(os.path.join(ROOT, 'pets'), prefix='pets', excludes=EXCL),
         Tree(os.path.join(ROOT, 'licenses'), prefix='licenses', excludes=EXCL),   # LGPL / GPL texts for Qt
         [('LICENSE', os.path.join(ROOT, 'LICENSE'), 'DATA'),
          ('THIRD_PARTY_NOTICES.md', os.path.join(ROOT, 'THIRD_PARTY_NOTICES.md'), 'DATA')]]

a = Analysis(
    [os.path.join(ROOT, 'packaging', 'launch.py')],
    pathex=[ROOT],
    hiddenimports=['numpy', 'json', 'math', 'random', 'statistics', 'dataclasses', 'logging'],
    excludes=['tkinter', 'matplotlib', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtQuick3D',
              'PySide6.QtCharts', 'PySide6.QtDataVisualization'],
    noarchive=False,
)
# Trim what a QtWebEngine widget app never loads (~110 MB): QML modules (and the Quick 3D / Controls libraries they
# pull in) and Qt's UI translations. Chromium keeps its en-US locale; other system locales fall back to it.
DROP_DIRS = ('PySide6/qml/', 'PySide6/translations/')
KEEP = ('PySide6/translations/qtwebengine_locales/en-US.pak',)
DROP_LIBS = ('Qt6Quick3D', 'Qt6QuickControls2', 'Qt6QuickDialogs2', 'Qt6LabsStyleKit', 'Qt6ShaderTools', 'Qt6Charts',
             'Qt6Graphs', 'Qt6DataVisualization', 'Qt63D', 'Qt6QuickTimeline', 'Qt6QuickParticles', 'Qt6VirtualKeyboard')


def _keep(entry):
    """Windows / Linux: drop the unused Qt6*.dll / libQt6*.so files (verified with the Windows exe --selftest).
    macOS: Qt ships as QtXxx.framework bundles; they are deliberately NOT trimmed (the macOS app is untested on
    real hardware, and a missing framework would stop it at launch) - only the QML / translation folders go."""
    dest = entry[0].replace('\\', '/')
    if dest in KEEP:
        return True
    if any(dest.startswith(d) for d in DROP_DIRS):
        return False
    base = dest.rsplit('/', 1)[-1]
    return not any(base.startswith(x) or base.startswith('lib' + x) for x in DROP_LIBS)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME, console=False, upx=False,
          icon=ICO if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, *datas, strip=False, upx=False, name=APP_NAME)

if sys.platform == 'darwin':
    app = BUNDLE(coll, name=f'{APP_NAME}.app', icon=ICNS, bundle_identifier='io.github.desktoppets3d',
                 info_plist={'CFBundleShortVersionString': __version__, 'CFBundleVersion': __version__,
                             'LSUIElement': True,                 # a desktop companion: no Dock icon, no menu bar
                             'NSHighResolutionCapable': True})
