"""Frame trace of the live pet: what the rig did every rendered frame (lid angle, eye angles, pupil, blink amount,
gaze weight, body yaw) next to the engine's output. For hunting 'glitches' that single screenshots cannot show.

    C:\\Python315\\python.exe -m app.trace <out.json> [--secs 40] [--cursor wander|scratch|still|far] [--size S]
                                                [--clip rest_one_leg]   (hold one clip, engine frozen)

The emotion engine runs live (nothing forced); only the cursor is virtual. Prints per clip the largest frame-to-frame
jumps and counts pupil-pinning and blink events, then the clip timeline.
"""
import json
import math
import os
import sys
import tempfile
import time

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'trace.json')
os.environ.setdefault('DP3D_DATA', tempfile.mkdtemp(prefix='dp3d_trace_'))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from . import paths  # noqa: E402
from .asset_server import AssetServer  # noqa: E402
from .desktop import PetWindow, setup_logging  # noqa: E402
from .registry import discover  # noqa: E402
from .storage import Settings  # noqa: E402


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def analyse(rows, engine):
    by = {}
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        if a[1] != b[1]:
            continue
        d = by.setdefault(b[1], dict(frames=0, lid=0.0, ey=0.0, ep=0.0, pin=0.0, pin_on=0, blinks=0, body=0.0,
                                     lidmix=0.0, headmix=0.0, pops=0))
        d['frames'] += 1
        for k, j in (('lid', 2), ('ey', 3), ('ep', 4), ('pin', 5), ('body', 8), ('lidmix', 10), ('headmix', 11)):
            d[k] = max(d[k], abs(b[j] - a[j]))
        if i + 1 < len(rows) and rows[i + 1][1] == b[1]:          # a one/two-frame dip of the clip's own head pose
            c = rows[i + 1]
            if a[11] - b[11] > 4 and c[11] - b[11] > 4:
                d['pops'] += 1
        if a[5] < 0.05 <= b[5]:
            d['pin_on'] += 1
        if a[6] < 0.3 <= b[6]:
            d['blinks'] += 1
    print(f"{'clip':22s} {'frames':>6s} {'max d/frame:':>12s} {'lid':>6s} {'eyeY':>6s} {'eyeP':>6s} {'pupil':>6s} {'body':>6s}"
          f" {'pin on':>7s} {'blinks':>6s} {'lidMix':>7s} {'headMix':>7s} {'pops':>5s}")
    for c, d in sorted(by.items(), key=lambda kv: -kv[1]['frames']):
        print(f"{c:22s} {d['frames']:6d} {'':12s} {d['lid']:6.2f} {d['ey']:6.2f} {d['ep']:6.2f} {d['pin']:6.3f} "
              f"{d['body']:6.2f} {d['pin_on']:7d} {d['blinks']:6d} {d['lidmix']:7.2f} {d['headmix']:7.2f} {d['pops']:5d}")
    tl, last = [], None
    for r in rows:
        if r[1] != last:
            tl.append(f'{(r[0] - rows[0][0]) / 1000:5.1f}s {r[1]}/{r[9]}')
            last = r[1]
    print('timeline:', ' | '.join(tl))
    pins = [o for o in engine if o['pin'] > 0]
    print(f'engine: pupil pin > 0 in {len(pins)}/{len(engine)} ticks; excited max '
          f'{max((o["excited"] for o in engine), default=0):.2f}; blinks sent {sum(1 for o in engine if o["blink"])}; '
          f'saccades {sum(1 for o in engine if o["sacc"])}')


def main():
    app = QApplication(sys.argv)
    setup_logging()
    spec = next(s for s in discover() if s.id == arg('--pet', 'sun_conure'))
    settings = Settings()
    settings.pet(spec.id)['pos'] = None
    settings.pet(spec.id)['size'] = arg('--size', 'S')
    server = AssetServer(paths.ROOT).start()
    w = PetWindow(spec, server, settings)
    g = QGuiApplication.primaryScreen().availableGeometry()
    w.move(g.left() + 40, g.bottom() - w.height())
    secs = float(arg('--secs', '40'))
    mode = arg('--cursor', 'wander')
    engine = []

    def head():
        f, px = w._frame(), w.pet_px()
        return w.width() / 2, w.height() - f['feet'] * px - 0.8 * px

    def cursor(t):
        hx, hy = head()
        px = w.pet_px()
        if mode == 'far':
            return {'x': -3000, 'y': -3000}
        if mode == 'still':
            return {'x': hx + 1.2 * px, 'y': hy - 0.4 * px}
        if mode == 'scratch':                       # bursts of up-down scratching with pauses resting on the head
            on = (t % 4.0) < 2.6
            return {'x': hx, 'y': hy + (0.1 * px * math.sin(2 * math.pi * 1.5 * t) if on else 0.0)}
        return {'x': hx + 1.3 * px * math.cos(2 * math.pi * t / 7.0),           # wander: slow ordinary movement
                'y': hy + 0.3 * px + 0.5 * px * math.sin(2 * math.pi * t / 5.0)}

    def hook():
        orig = w.engine.update

        def upd(dt, p):
            o = orig(dt, p)
            engine.append(dict(pin=o['face']['pupil_small'], excited=o['emotions']['excited'], blink=o.get('blink'),
                               sacc=o['gaze']['saccade'], clip=o['clip']))
            return o
        w.engine.update = upd

    def done(data):
        rows = data['rows']
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(dict(rows=rows, engine=engine), f)
        analyse(rows, engine)
        app.exit(0)

    def go(t0=time.monotonic()):
        if not w.loaded:
            if time.monotonic() - t0 > 30:
                print('TRACE FAILED: model did not load')
                return app.exit(2)
            return QTimer.singleShot(200, go)
        hook()
        w.on_trace = done
        start = time.monotonic()
        w.override = {'cursor_fn': lambda now: cursor(now - start)}
        clip = arg('--clip')
        if clip:                                    # hold one clip (engine frozen; rig, gaze, blinks stay live)
            w.override.update(freeze=True, out=dict(clip=clip, clip_time=0.0, changed=True, loop=True, crossfade=0.2,
                                                    behaviour='rest', emotions={'content': 0.8},
                                                    face={'lid_droop': 0.3}, gaze={'cursor_weight': 1.0},
                                                    follow={'mode': 'watch'}, sounds=[], fx=[]))
        w.bridge.send({'type': 'debug_trace', 'frames': int(secs * 60)})

    QTimer.singleShot(200, go)
    code = app.exec()
    server.stop()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
