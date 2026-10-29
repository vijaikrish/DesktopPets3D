"""Operating-system services the desktop host needs, behind one small API (Windows, macOS, Linux/X11).

  idle_seconds()                  seconds since the user last touched mouse / keyboard (user presence)
  local_hour()                    local clock as a float hour 0..24
  set_click_through(widget, on)   the window lets clicks through to whatever is below (True) or catches them
  is_click_through(widget)        current state (review tool)
  prepare_window(widget)          per-OS window attributes for an always-on-top desktop companion

Windows: Win32 via ctypes (GetLastInputInfo; WS_EX_TRANSPARENT on the layered window) - see win32.py.
macOS:   CoreGraphics idle time via ctypes (macos.py); click-through with Qt's WindowTransparentForInput on the
         QWindow, which Qt maps to NSWindow.ignoresMouseEvents without re-creating the window.
Linux:   same Qt flag (X11 input shape); idle time from cursor movement only.
Only Windows is tested on real hardware; macOS / Linux paths are written to the platform APIs but unverified here.
"""
import sys
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'

if IS_WIN:
    from . import win32 as _win
else:
    _win = None
if IS_MAC:
    from . import macos as _mac
else:
    _mac = None

_cursor = {'pos': None, 't': time.monotonic()}


def _cursor_idle():
    """Fallback presence: seconds since the cursor last moved (keyboard activity is not seen)."""
    p = QCursor.pos()
    now = time.monotonic()
    if _cursor['pos'] != (p.x(), p.y()):
        _cursor['pos'], _cursor['t'] = (p.x(), p.y()), now
    return now - _cursor['t']


def idle_seconds():
    if IS_WIN:
        return _win.idle_seconds()
    if IS_MAC:
        v = _mac.idle_seconds()
        if v is not None:
            return v
    return _cursor_idle()


def local_hour(t=None):
    lt = time.localtime(t)
    return lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0


def set_click_through(widget, on):
    if IS_WIN:
        return _win.set_click_through(int(widget.winId()), on)
    wh = widget.windowHandle()
    if wh is None:
        return False
    flag = Qt.WindowType.WindowTransparentForInput
    if bool(wh.flags() & flag) != bool(on):
        wh.setFlag(flag, bool(on))
    return True


def is_click_through(widget):
    if IS_WIN:
        return _win.is_click_through(int(widget.winId()))
    wh = widget.windowHandle()
    return bool(wh and wh.flags() & Qt.WindowType.WindowTransparentForInput)


def prepare_window(widget):
    """Attributes every pet / panel window gets. macOS: keep tool windows visible while another app is active."""
    if IS_MAC:
        attr = getattr(Qt.WidgetAttribute, 'WA_MacAlwaysShowToolWindow', None)
        if attr is not None:
            widget.setAttribute(attr, True)
