"""Visual review harness for a pet plugin (run before calling any visual change done).

    C:\\Python315\\python.exe -m app.review <outdir> [--pet sun_conure] [--variant female] [--only eyes,e2e]

Opens a real PetWindow with isolated data (DP3D_DATA = <outdir>/data), freezes the emotion engine and drives it with
forced clips, cursor positions and effects. Each step saves the page's own pixels (3D canvas + effects canvas, with
alpha) and the hit-test result. Writes:
  sheet_sizes.png  Small / Medium / Large over a light and a dark desktop
  sheet_gaze.png   cursor at 9 positions around the head (head, eyes, +-30 deg body turn)
  sheet_moods.png  emotion clips with their 2D effects
  review.json      per step: fps, over/zone under the cursor, click-through state, window size
Exit code 0 when every hit-test / click-through check passes.
"""
import base64
import json
import os
import sys
import time

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'review_out')
os.makedirs(OUT, exist_ok=True)
os.environ.setdefault('DP3D_DATA', os.path.join(OUT, 'data'))

from PySide6.QtCore import QRect, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from . import paths  # noqa: E402
from .asset_server import AssetServer  # noqa: E402
from .desktop import PetWindow, setup_logging  # noqa: E402
from .registry import discover  # noqa: E402
from .storage import Settings  # noqa: E402
from .osapi import is_click_through  # noqa: E402


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def mood(clip, behaviour='rest', emotions=None, face=None, look=1.0, fx=(), stream=(), levels=None, cursor=(0.0, -1.6)):
    return dict(clip=clip, behaviour=behaviour, emotions=emotions or {}, face=face or {}, look=look, fx=list(fx),
                stream=list(stream), levels=levels or {}, cursor=cursor)


MOODS = [
    ('content - idle', mood('idle_breathe', emotions={'content': 0.7})),
    ('wants a scratch', mood('ask_head_scratch', 'affection', {'affectionate': 0.8}, cursor=(0.05, -0.15))),
    ('head scratched', mood('head_scratched', 'enjoy_petting', {'affectionate': 0.95, 'content': 0.8},
                            {'lid_droop': 0.8}, look=0.2, stream=[('heart', 0.45), ('sparkle', 0.3)], cursor=(0.0, -0.05))),
    ('belly tap: a bit angry', mood('angry_puff', 'threaten', {'angry': 0.45}, {'pupil_small': 0.9},
                                    stream=[('smoke', 0.35), ('anger', 0.6)], cursor=(0.0, 0.55))),
    ('warning lunge', mood('warn_lunge', 'threaten', {'angry': 0.7}, {'pupil_small': 1.0}, stream=[('anger', 0.5)],
                           cursor=(0.0, 0.5))),
    ('sad - rain cloud', mood('sad_idle', 'mope', {'sad': 0.85}, look=0.1, stream=[('tear', 0.6)],
                              levels={'rain_cloud': 0.9})),
    ('singing', mood('talk', 'chatter', {'happy': 0.7}, stream=[('note', 0.3)])),
    ('dancing - leaves', mood('happy_dance', 'play', {'playful': 0.8, 'happy': 0.7},
                              stream=[('leaf', 0.3), ('petal', 0.45), ('note', 0.5)])),
    ('bored - dry leaves', mood('bored_sigh', 'bored_idle', {'bored': 0.7}, look=0.2, stream=[('leaf_dry', 0.4)])),
    ('startled', mood('startle_flinch', 'startle', {'startled': 0.9}, fx=[('exclaim', 1)])),
    ('curious', mood('curious_tilt', 'investigate', {'curious': 0.8}, fx=[('question', 1)], cursor=(1.2, -1.0))),
    ('asleep', mood('sleep', 'sleep', {'sleepy': 0.9}, look=0.0, stream=[('zzz', 0.8)])),
]
GAZE = [('up-left', (-1.6, -1.6)), ('up', (0.0, -1.8)), ('up-right', (1.6, -1.6)),
        ('left', (-2.0, 0.0)), ('at the bird', (0.0, -0.05)), ('right', (2.0, 0.0)),
        ('down-left', (-1.6, 1.2)), ('down', (0.0, 1.4)), ('down-right', (1.6, 1.2))]


class Review:
    def __init__(self, app, win):
        self.app, self.w = app, win
        self.rows = []
        self.imgs = {}
        self.steps = []
        self._stream = None
        self.fails = []
        self._collect = None
        self._tokens = set()
        self._js_max = dict(speed=0.0, jitter=0.0)

    # geometry helpers (window-local px; head ~0.8 pet heights above the feet line)
    def head_xy(self):
        f = self.w._frame()
        px = self.w.pet_px()
        return self.w.width() / 2, self.w.height() - f['feet'] * px - 0.8 * px

    def at(self, rel):
        hx, hy = self.head_xy()
        px = self.w.pet_px()
        return {'x': hx + rel[0] * px, 'y': hy + rel[1] * px}

    def force(self, m):
        out = dict(clip=m['clip'], clip_time=0.0, changed=True, loop=True, crossfade=0.15, behaviour=m['behaviour'],
                   emotions=m['emotions'], face=m['face'], gaze={'cursor_weight': m['look'], 'saccade': False},
                   follow={'mode': 'none' if m['behaviour'] == 'sleep' else 'watch'}, sounds=[], fx=[])
        self.w.bridge.send({'type': 'fx_clear'})
        self.w.override = {'freeze': True, 'out': out, 'cursor': self.at(m['cursor']),
                           'levels': dict(m['levels']) or {'rain_cloud': 0.0}}
        self._late = [dict(kind=k, anchor=None, count=n, size=1.0) for k, n in m['fx']]   # spawned 0.45 s before the shot
        self._streams = [[k, every, 0.0] for k, every in m['stream']]

    def add(self, group, tag, setup, wait=2.2, check=None):
        self.steps.append(dict(group=group, tag=tag, setup=setup, wait=wait, check=check))

    def build(self):
        for key in ('S', 'M', 'L'):
            self.add('sizes', f'{key} ({self.w._sizes()[key]} px)',
                     lambda k=key: (self.w.set_size(k), self.force(mood('idle_breathe', cursor=(0.0, -0.05)))), 2.5)
        self.add('gaze', 'reset', lambda: (self.w.set_size('M'), self.force(mood('idle_breathe'))), 1.0)
        for name, rel in GAZE:
            self.add('gaze', name, lambda r=rel: self.force(mood('idle_breathe', cursor=r)), 2.6)
        for name, m in MOODS:
            self.add('moods', name, lambda mm=m: self.force(mm), 2.4)
        # close-ups (XL = review-only size) of the face: beak seam, eyes and lids with the head turned both ways
        self.w.spec.m['stage']['sizes']['XL'] = 420
        for name, rel in (('face: cursor left', (-2.0, 0.0)), ('face: front', (0.0, -0.05)),
                          ('face: cursor right', (2.0, 0.0)), ('face: blink', (0.0, -0.05))):
            self.add('closeup', name, lambda r=rel, n=name: (self.w.set_size('XL'), self.force(mood('idle_breathe', cursor=r)),
                                                           n.endswith('blink') and QTimer.singleShot(2280, lambda: self.w.bridge.send(
                                                               {'type': 'debug_blink'}))), 2.4)
        self.add('closeup', 'reset', lambda: (self.w.set_size('M'), self.force(mood('idle_breathe'))), 1.0)
        # eyes under half-closed lids (rest_one_leg holds the upper lids ~35 % closed): the iris must never slide into
        # the lid shell when the bird glances at the cursor. Shot at clip time ~1.2 s (before its baked blink).
        for name, rel in (('one leg: cursor up', (0.0, -1.8)), ('one leg: up-left', (-1.6, -1.6)),
                          ('one leg: at the bird', (0.0, -0.05)), ('one leg: right', (2.0, 0.0)),
                          ('one leg: down', (0.0, 1.4))):
            self.add('eyes', name, lambda r=rel: (self.w.set_size('XL'), self.force(
                mood('rest_one_leg', emotions={'content': 0.8}, face={'lid_droop': 0.3}, cursor=r))), 1.2)
        self.add('eyes', 'reset', lambda: (self.w.set_size('M'), self.force(mood('idle_breathe'))), 1.0)
        # hit tests: cursor over head / belly / wing / empty corner -> zone + click-through state
        for name, rel, want_over, zones in (('hit head', (0.0, 0.0), True, ('head', 'crown', 'cheek')),
                                            ('hit belly', (0.0, 0.55), True, ('belly', 'chest')),
                                            ('hit empty', (-0.9, -0.6), False, (None,))):
            self.add('hits', name, lambda r=rel: self.force(mood('idle_breathe', cursor=r)), 1.2,
                     check=(want_over, zones))

    def build_v5(self):
        """v5: flight (live engine; no cropping at the top, it really rises), the mood panel window, lip-sync beak."""
        def fly(k):
            self.w.set_size(k)
            self.w.override = {'cursor': self.at((1.6, -1.2))}
            self.w.bridge.send({'type': 'fx_clear'})
            QTimer.singleShot(300, lambda: self.w.engine and self.w.engine.event('fly'))

        for k in ('S', 'L'):
            self.add('fly', f'{k}: standing', lambda kk=k: (self.w.set_size(kk), self.force(mood('idle_breathe'))), 1.5,
                     check=('alpha', 'ground'))
            self.add('fly', f'{k}: take-off +0.7 s', lambda kk=k: fly(kk), 1.0, check=('alpha', 'any'))
            self.add('fly', f'{k}: hover +2.0 s', lambda: None, 1.3, check=('alpha', 'up'))
            self.add('fly', f'{k}: hover +3.4 s', lambda: None, 1.4, check=('alpha', 'up'))
            self.add('fly', f'{k}: landing +4.6 s', lambda: None, 1.2, check=('alpha', 'any'))
            self.add('fly', f'{k}: landed +6.0 s', lambda: None, 1.4, check=('alpha', 'ground'))

        def panel():
            self.w.set_size('S')
            self.w.override = {'cursor': self.at((1.6, -1.2))}
            m = getattr(self.w.engine, 'mind', None)
            if m is not None:
                self._panel_saved_drives = (m.sleep_debt, m.hunger)
                m.sleep_debt, m.hunger = 0.62, 0.42
            self.w._set_panel(True)
        self.add('panel', 'panel: hungry + sleep-deprived', panel, 4.0, check=('panel', None))
        def reset_panel():
            m = getattr(self.w.engine, 'mind', None)
            if m is not None and hasattr(self, '_panel_saved_drives'):
                m.sleep_debt, m.hunger = self._panel_saved_drives
            self.w._set_panel(False)
            self.force(mood('idle_breathe'))
        self.add('panel', 'reset', reset_panel, 1.0)
        for deg in (0, 18, 20, 22, 28):
            self.add('beak', f'S: jaw {deg} deg', lambda d=deg: (self.w.set_size('S'), self.force(mood('idle_breathe', cursor=(0.0, -0.05))),
                                                              self.w.bridge.send({'type': 'debug_jaw', 'deg': d})), 1.6)
        self.add('beak', 'reset', lambda: (self.w.bridge.send({'type': 'debug_jaw', 'deg': None}),
                                           self.force(mood('idle_breathe'))), 0.8)

    def build_e2e(self):
        """Live engine (not frozen): virtual cursor -> JS touch/kinematics -> core -> ConureMind -> clip.
        The cursor is computed per 60 Hz tick (cursor_fn), so speed and jitter are measured like a real mouse."""
        import math
        px = self.w.pet_px

        def start(fn):
            self.w.bridge.send({'type': 'fx_clear'})
            self.w.override = {'cursor_fn': fn}
            self._collect, self._tokens, self._js_max = [], set(), dict(speed=0.0, jitter=0.0)

        def C():
            return self._collect

        def scratch():                      # cursor moving up and down over the head, 1.5 Hz, +-0.1 pet heights
            head = self.at((0.0, 0.02))
            start(lambda t: {'x': head['x'], 'y': head['y'] + 0.1 * px() * math.sin(2 * math.pi * 1.5 * t)})

        def scratch_check():
            beh = {r['b'] for r in C()}
            clips = {r['clip'] for r in C()}
            aff = max((r['aff'] for r in C()), default=0)
            ang = max((r['angry'] for r in C()), default=0)
            return ('enjoy_petting' in beh and 'head_scratched' in clips and aff > 0.6 and ang < 0.1,
                    f'behaviours={sorted(beh)} affectionate_max={aff:.2f} angry_max={ang:.2f} '
                    f'js_speed_max={self._js_max["speed"]:.0f} jitter_max={self._js_max["jitter"]:.1f}')

        def wander():                       # ordinary mouse use around the bird, crossing its body now and then
            c = self.at((0.0, 0.45))
            start(lambda t: {'x': c['x'] + 1.0 * px() * math.cos(2 * math.pi * t / 3.2),
                             'y': c['y'] + 0.55 * px() * math.sin(4 * math.pi * t / 3.2)})

        def wander_check():
            beh = {r['b'] for r in C()}
            ang = max((r['angry'] for r in C()), default=0)
            joy = max((max(r['happy'], r['playful']) for r in C()), default=0)
            return (ang < 0.1 and joy > 0.4 and not beh & {'threaten', 'avoid_hand', 'fear'},
                    f'angry_max={ang:.2f} happy/playful_max={joy:.2f} behaviours={sorted(beh)} '
                    f'js_speed_max={self._js_max["speed"]:.0f} jitter_max={self._js_max["jitter"]:.1f}')

        def scrub():                        # frantic: +-0.5 pet heights at 7 Hz right over the head
            head = self.at((0.0, 0.02))
            start(lambda t: {'x': head['x'] + 0.5 * px() * math.sin(2 * math.pi * 7 * t), 'y': head['y']})

        def scrub_check():
            ang = max((r['angry'] for r in C()), default=0)
            clips = {r['clip'] for r in C()}
            return (0.05 <= ang <= 0.45 and not clips & {'warn_lunge', 'angry_full'},
                    f'angry_max={ang:.2f} (a bit) lunges={sorted(clips & {"warn_lunge", "angry_full"})} '
                    f'annoyed_mark={"annoyed" in self._tokens} js_speed_max={self._js_max["speed"]:.0f} '
                    f'jitter_max={self._js_max["jitter"]:.1f}')

        def belly():
            b = self.at((0.0, 0.55))
            start(lambda t: b)
            QTimer.singleShot(1500, lambda: self.w.bridge.send({'type': 'debug_click', **b}))

        def belly_check():
            # 'a bit angry', as seen and heard: pulls away or threatens + anger mark + grumble, anger clearly up
            after = C()[int(len(C()) * 0.25):]
            beh = {r['b'] for r in after}
            ang = max((r['angry'] for r in after), default=0)
            ok = bool(beh & {'avoid_hand', 'threaten'}) and {'anger', 'grumble'} <= self._tokens and ang > 0.2
            return ok, f'behaviours={sorted(beh)} angry_max={ang:.2f} feedback={sorted(self._tokens & {"anger", "grumble"})}'

        def calm():
            start(lambda t: self.at((-0.9, -0.6)))

        self.add('e2e', 'live: scratch the head', scratch, 8.0, check=('custom', scratch_check))
        self.add('e2e', 'live: move around (no click)', wander, 8.0, check=('custom', wander_check))
        self.add('e2e', 'live: frantic scrub +3 s', scrub, 3.0)
        self.add('e2e', 'live: frantic scrub +6 s', lambda: None, 3.0, check=('custom', scrub_check))
        self.add('e2e', 'calm down', calm, 6.0)
        self.add('e2e', 'live: belly click +0.9 s', belly, 2.4)                    # the reaction itself
        self.add('e2e', 'live: belly click +3.5 s', lambda: None, 2.6, check=('custom', belly_check))

    def _hook_engine(self):
        """Record EVERY engine output (60 Hz). One-frame tokens (fx 'anger', sound 'grumble') would be missed by
        sampling the window's last output at the 20 Hz harness rate."""
        eng = self.w.engine
        if eng is None or getattr(eng, '_review_hooked', False):
            return
        orig = eng.update

        def update(dt, percepts):
            o = orig(dt, percepts)
            if self._collect is not None and isinstance(o, dict):
                em = o.get('emotions') or {}
                self._collect.append(dict(b=o.get('behaviour'), clip=o.get('clip'), angry=em.get('angry', 0.0),
                                          aff=em.get('affectionate', 0.0), happy=em.get('happy', 0.0),
                                          playful=em.get('playful', 0.0)))
                self._tokens.update(o.get('fx') or [])
                self._tokens.update(o.get('sounds') or [])
                for k, pk in (('speed', 'cursor_speed'), ('jitter', 'cursor_jitter')):
                    self._js_max[k] = max(self._js_max[k], float(percepts.get(pk) or 0.0))
            return o
        eng.update = update
        eng._review_hooked = True

    def run(self):
        self.build()
        self.build_v5()
        if '--no-e2e' not in sys.argv:
            self._hook_engine()
            self.build_e2e()
        only = arg('--only')                       # e.g. --only eyes,e2e : run just these groups
        if only:
            keep = set(only.split(','))
            self.steps = [st for st in self.steps if st['group'] in keep]
        self._tick = QTimer()
        self._tick.timeout.connect(self._feed)
        self._tick.start(50)
        QTimer.singleShot(0, self._next)

    def _feed(self):
        ov = self.w.override
        if not ov:
            return
        now = time.monotonic()
        for s in getattr(self, '_streams', []):
            if now >= s[2]:
                s[2] = now + s[1]
                ov.setdefault('fx', []).append(dict(kind=s[0], anchor=None, count=1, size=1.0))

    def _next(self):
        if not self.steps:
            return self.finish()
        st = self.steps.pop(0)
        self._late = []
        st['setup']()
        QTimer.singleShot(max(0, int((st['wait'] - 0.45) * 1000)), self._spawn_late)
        QTimer.singleShot(int(st['wait'] * 1000), lambda: self._snap(st))

    def _spawn_late(self):
        if self.w.override is not None and self._late:
            self.w.override.setdefault('fx', []).extend(self._late)
            self._late = []

    def _snap(self, st):
        self.w.on_snapshot = lambda data: self._got(st, data)
        self.w.snapshot(st['tag'])

    def _got(self, st, data):
        self.w.on_snapshot = None
        png = base64.b64decode(data['png'].split(',', 1)[1])
        fn = os.path.join(OUT, f"{st['group']}_{len(self.rows):02d}.png")
        with open(fn, 'wb') as f:
            f.write(png)
        ct = is_click_through(self.w)
        row = dict(group=st['group'], tag=st['tag'], file=fn, fps=data.get('fps'), over=data.get('over'),
                   zone=data.get('zone'), click_through=ct, window=[self.w.width(), self.w.height()])
        if st['check'] and st['check'][0] == 'panel':
            fn = os.path.join(OUT, f"panel_{len(self.rows):02d}.png")
            self.w.panel.grab().save(fn)
            row['file'] = fn
            ok = self.w.panel.isVisible() and self.w.panel.snapshot_values().get('m1', 0) > 0.5
            row['check'] = ('PASS ' if ok else 'FAIL ') + f"panel {self.w.panel.width()}x{self.w.panel.height()} " \
                f"values={ {k: round(v, 2) for k, v in self.w.panel.snapshot_values().items() if k[0] == 'm'} }"
            if not ok:
                self.fails.append(row)
        elif st['check'] and st['check'][0] == 'alpha':
            # Measure only the model: floating FX can touch the top or lie below the feet.
            model_fn = os.path.join(OUT, f"model_{len(self.rows):02d}.png")
            with open(model_fn, 'wb') as f:
                f.write(base64.b64decode(data['modelPng'].split(',', 1)[1]))
            top, bottom, ih = alpha_rows(model_fn)
            k = ih / max(1, self.w.height())                    # canvas px per window px (device pixel ratio)
            top, bottom = (None, None) if top is None else (top / k, bottom / k)
            px = self.w.pet_px()
            ground = self.w.height() - self.w._frame()['feet'] * px
            lift = (ground - bottom) / px if bottom is not None else 0.0   # feet above the feet line (pet heights)
            want = st['check'][1]
            lift = lift if top is not None else 0.0
            top = top if top is not None else -1.0
            ok = top > 2 and (want == 'any' or (want == 'up' and lift > 0.25)
                                                  or (want == 'ground' and lift < 0.08))
            row['check'] = ('PASS ' if ok else 'FAIL ') + f'top_px={top:.0f} feet_lift={lift:.2f} pet heights ({want})'
            if not ok:
                self.fails.append(row)
        elif st['check'] and st['check'][0] == 'custom':
            ok, detail = st['check'][1]()
            row['check'] = ('PASS ' if ok else 'FAIL ') + detail
            self._collect = None
            if not ok:
                self.fails.append(row)
        elif st['check']:
            want_over, zones = st['check']
            ok = (row['over'] == want_over) and (row['zone'] in zones) and (ct == (not want_over))
            row['check'] = 'PASS' if ok else 'FAIL'
            if not ok:
                self.fails.append(row)
        self.rows.append(row)
        if st['tag'] not in ('reset', 'calm down'):
            self.imgs.setdefault(st['group'], []).append((st['tag'], QImage(fn)))
        QTimer.singleShot(0, self._next)

    def finish(self):
        self._tick.stop()
        for group, items in self.imgs.items():
            if group not in ('hits',):
                sheet(items, os.path.join(OUT, f'sheet_{group}.png'), dual=(group == 'sizes'))
        with open(os.path.join(OUT, 'review.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(load=self.w.load_info, rows=self.rows, fails=self.fails), f, indent=1)
        print('REVIEW', 'OK' if not self.fails else 'FAILED', OUT)
        for r in self.rows:
            print(f"  {r['group']:6s} {r['tag']:24s} fps={r['fps']} over={r['over']} zone={r['zone']} "
                  f"click_through={r['click_through']} {r.get('check', '')}")
        self.app.exit(0 if not self.fails else 1)


def alpha_rows(fn, thr=90):
    """(first, last) image row containing bird pixels (alpha > thr: the soft shadow is ~56). None if empty."""
    img = QImage(fn).convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    import numpy as np
    a = np.frombuffer(img.constBits(), np.uint8, count=img.bytesPerLine() * h).reshape(h, img.bytesPerLine())
    a = a[:, 3:w * 4:4]
    rows = np.where((a > thr).any(axis=1))[0]
    return (int(rows[0]), int(rows[-1]), h) if len(rows) else (None, None, h)


def sheet(items, path, dual=False):
    """Contact sheet: each frame over a desktop-like background (light + dark when dual) with its label."""
    cw = max(i.width() for _, i in items)
    ch = max(i.height() for _, i in items)
    cols = len(items) if dual else min(4, len(items))
    rows_n = (2 if dual else 1) * ((len(items) + cols - 1) // cols)
    W, H = cols * cw, rows_n * (ch + 26)
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(QColor('#20242c'))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setFont(QFont('Segoe UI', 11))
    bgs = [('#3b6ea5', '#86b3d9'), ('#e9e4da', '#c9c2b4')] if dual else [('#3b6ea5', '#86b3d9')]
    for bi, (top, bot) in enumerate(bgs):
        for k, (label, im) in enumerate(items):
            r, c = divmod(k, cols)
            r += bi * ((len(items) + cols - 1) // cols)
            x, y = c * cw, r * (ch + 26)
            g = QLinearGradient(0, y, 0, y + ch)
            g.setColorAt(0, QColor(top)); g.setColorAt(1, QColor(bot))
            p.fillRect(QRect(x, y, cw, ch), g)
            p.drawImage(x + (cw - im.width()) // 2, y + ch - im.height(), im)
            p.setPen(QColor('#ffffff'))
            p.drawText(QRect(x, y + ch, cw, 26), int(Qt.AlignmentFlag.AlignCenter), label)
    p.end()
    img.save(path)


def main():
    app = QApplication(sys.argv)
    setup_logging()
    pid = arg('--pet', 'sun_conure')
    spec = next(s for s in discover() if s.id == pid)
    settings = Settings()
    if arg('--variant'):
        settings.pet(pid)['variant'] = arg('--variant')
    settings.pet(pid)['pos'] = None
    server = AssetServer(paths.ROOT).start()
    w = PetWindow(spec, server, settings)
    g = QGuiApplication.primaryScreen().availableGeometry()
    w.move(g.left() + 40, g.bottom() - w.height())
    rv = Review(app, w)

    def wait_loaded(t0=time.monotonic()):
        if w.loaded:
            return rv.run()
        if time.monotonic() - t0 > 30:
            print('REVIEW FAILED: model did not load')
            return app.exit(2)
        QTimer.singleShot(200, wait_loaded)

    QTimer.singleShot(200, wait_loaded)
    code = app.exec()
    server.stop()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
