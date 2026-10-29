"""CPU / RAM probe for the running app (pure ctypes, no psutil).

    C:\\Python315\\python.exe tools\\perf_probe.py [seconds=15] [--size S|M|L] [--tick 16]

Starts the app with isolated data, waits for the model to load, then measures CPU time of the app process and all
its QtWebEngineProcess children over the window. Prints % of ONE core and working-set MB, then stops the app.
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t)]


def children(pid):
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    out = []
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.th32ParentProcessID == pid:
            out.append((e.th32ProcessID, e.szExeFile))
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def times(pid):
    h = k32.OpenProcess(0x1000 | 0x0400, False, pid)
    if not h:
        return None, 0
    c, x, kt, ut = (wintypes.FILETIME() for _ in range(4))
    k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(kt), ctypes.byref(ut))
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    k32.CloseHandle(h)
    ft = lambda f: (f.dwHighDateTime << 32 | f.dwLowDateTime) / 1e7
    return ft(kt) + ft(ut), pmc.WorkingSetSize / 2 ** 20


def main():
    a = [x for x in sys.argv[1:]]
    secs = float(a[0]) if a and not a[0].startswith('--') else 15.0
    size = a[a.index('--size') + 1] if '--size' in a else 'S'
    data = tempfile.mkdtemp(prefix='dp3d_perf_')
    os.makedirs(os.path.join(data), exist_ok=True)
    with open(os.path.join(data, 'settings.json'), 'w') as f:
        json.dump({'pets': {'sun_conure': {'size': size}}}, f)
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
    env['DP3D_DATA'] = data
    if '--tick' in a:
        env['DP3D_TICK_MS'] = a[a.index('--tick') + 1]
    p = subprocess.Popen([sys.executable, '-m', 'app.desktop'], cwd=ROOT, env=env)
    try:
        time.sleep(12)
        pids = [(p.pid, 'python.exe (host + browser)')] + children(p.pid)
        t0 = {pid: times(pid)[0] for pid, _ in pids}
        time.sleep(secs)
        tot, ram = 0.0, 0.0
        for pid, name in pids:
            t, mb = times(pid)
            if t is None or t0.get(pid) is None:
                continue
            pct = (t - t0[pid]) / secs * 100
            tot += pct
            ram += mb
            print(f'  {name:32s} pid {pid:6d}  cpu {pct:5.1f} % of one core   RAM {mb:6.0f} MB')
        print(f'TOTAL size={size} tick={env.get("DP3D_TICK_MS", "16")} ms: cpu {tot:.1f} % of one core '
              f'({tot / os.cpu_count():.2f} % of the machine), RAM {ram:.0f} MB')
    finally:
        p.kill()
        p.wait(10)


if __name__ == '__main__':
    main()
