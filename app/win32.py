"""Small Windows helpers (ctypes). Everything degrades gracefully on other platforms."""
import ctypes
import sys
import time
from ctypes import wintypes

_IS_WIN = sys.platform == 'win32'


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]


def idle_seconds():
    """Seconds since the last keyboard/mouse input anywhere in the session (user presence)."""
    if not _IS_WIN:
        return 0.0
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return max(0.0, ((now - lii.dwTime) & 0xFFFFFFFF) / 1000.0)


def local_hour(t=None):
    lt = time.localtime(t)
    return lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000


def set_click_through(hwnd, on):
    """Make a (layered) top-level window ignore the mouse entirely (clicks reach whatever is below) or not.

    Qt's translucent WebEngine window is hit-tested as a whole rectangle - transparent pixels are NOT click-through
    by themselves - so the app toggles this whenever the cursor enters/leaves the pet's silhouette."""
    if not _IS_WIN or not hwnd:
        return False
    u = ctypes.windll.user32
    get = getattr(u, 'GetWindowLongPtrW', u.GetWindowLongW)
    put = getattr(u, 'SetWindowLongPtrW', u.SetWindowLongW)
    get.restype, get.argtypes = ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int]
    put.restype, put.argtypes = ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    ex = get(hwnd, GWL_EXSTYLE)
    new = (ex | WS_EX_TRANSPARENT | WS_EX_LAYERED) if on else (ex & ~WS_EX_TRANSPARENT)
    if new != ex:
        put(hwnd, GWL_EXSTYLE, new)
    return True


def is_click_through(hwnd):
    if not _IS_WIN or not hwnd:
        return False
    u = ctypes.windll.user32
    get = getattr(u, 'GetWindowLongPtrW', u.GetWindowLongW)
    get.restype, get.argtypes = ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int]
    return bool(get(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT)
