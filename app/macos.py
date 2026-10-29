"""macOS helpers via ctypes (no PyObjC dependency). Imported only on macOS (sys.platform == 'darwin')."""
import ctypes
import ctypes.util

_CG = None
K_CG_EVENT_SOURCE_STATE_HID = 1          # kCGEventSourceStateHIDSystemState
K_CG_ANY_INPUT_EVENT = 0xFFFFFFFF        # kCGAnyInputEventType (~0)


def _cg():
    global _CG
    if _CG is None:
        path = ctypes.util.find_library('ApplicationServices') or \
            '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
        lib = ctypes.cdll.LoadLibrary(path)
        f = lib.CGEventSourceSecondsSinceLastEventType
        f.restype = ctypes.c_double
        f.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        _CG = lib
    return _CG


def idle_seconds():
    """Seconds since the last keyboard / mouse / trackpad input (CoreGraphics). None if unavailable."""
    try:
        return max(0.0, float(_cg().CGEventSourceSecondsSinceLastEventType(K_CG_EVENT_SOURCE_STATE_HID,
                                                                           K_CG_ANY_INPUT_EVENT)))
    except Exception:
        return None
