"""DesktopPets3D host: one transparent, always-on-top window per pet plugin.

Qt owns the OS side (window, click-through, dragging, menus, tray, timers, persistence) and runs the pet's emotion
engine at 60 Hz; the web page (web/pet.html) owns the pixels (3D model, procedural gaze, 2D effects, audio) and reports
touch input back. Nothing here is species-specific: sizes, menus, effects and the engine come from pets/<id>/pet.json.
"""
import base64
import json
import logging
import os
import sys
import time

from PySide6.QtCore import QLockFile, QObject, QPoint, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget

from . import APP_NAME, __version__, paths
from .asset_server import AssetServer
from .fx_director import FxDirector
from .plugin_api import normalize_output
from .registry import discover
from .sound_bank import SoundBank
from .osapi import idle_seconds, local_hour, prepare_window, set_click_through
from .panel import MoodPanel
from .storage import PetMemory, Settings

log = logging.getLogger('desktoppets3d')
SIZE_LABELS = {'S': 'Small', 'M': 'Medium', 'L': 'Large'}
DEFAULT_SIZES = {'S': 130, 'M': 190, 'L': 255}
DEFAULT_FRAME = {'width': 2.0, 'height': 1.95, 'feet': 0.2}
VOLUMES = (('Quiet', 0.4), ('Normal', 0.8), ('Loud', 1.0))
TICK_MS = int(os.environ.get('DP3D_TICK_MS', '16'))     # engine + messaging rate; rendering is always vsync (60 fps)


class Bridge(QObject):
    """Narrow JS <-> Python channel: JSON state out, named actions with plain data in. Nothing is evaluated."""
    readySig = Signal()
    stateSig = Signal(str)
    actionSig = Signal(str, 'QVariantMap')

    @Slot()
    def ready(self):
        self.readySig.emit()

    @Slot(str, 'QVariantMap')
    def actionData(self, name, data):
        self.actionSig.emit(name, dict(data))

    def send(self, msg):
        self.stateSig.emit(json.dumps(msg, separators=(',', ':')))


class PetPage(QWebEnginePage):
    LEVELS = {0: logging.DEBUG, 1: logging.WARNING, 2: logging.ERROR}

    def javaScriptConsoleMessage(self, level, message, line, source):
        log.log(self.LEVELS.get(getattr(level, 'value', level), logging.INFO), 'JS %s:%s %s', source, line, message)


class PetView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet('background: transparent')
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setPage(PetPage(self))
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)   # the pet may call first


class PetWindow(QWidget):
    def __init__(self, spec, server, settings, on_change=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.spec, self.server, self.settings, self.on_change = spec, server, settings, on_change
        self.pet_settings = settings.pet(spec.id)
        self.memory = PetMemory(spec.id)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        prepare_window(self)
        self.setWindowTitle(spec.name)
        self.view = PetView(self)
        self.bridge = Bridge()
        self.bridge.actionSig.connect(self._action)
        self.bridge.readySig.connect(self._on_ready)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject('pet', self.bridge)
        self.view.page().setWebChannel(self.channel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        # runtime state
        self.loaded = False
        self.load_info = {}
        self.frames_sent = 0
        self.override = None            # review tool: {'cursor': {x, y}, 'out': {...}, 'freeze': bool}
        self.on_snapshot = None
        self._initialised = False
        self._drag = None
        self._press_off = None
        self._drag_ended = False
        self._hover = False
        self._menu_open = False
        self._clickthrough = None
        self._ct_check = 0.0
        self.panel = None               # mood panel window (created on first show)
        self._js = dict(dist=None, approach=0.0, speed=0.0, jitter=0.0, over=False, zone=None, pet_px=None)
        self._out = normalize_output({})
        self.sound = SoundBank(spec)
        self.fx = FxDirector(spec)
        self.engine = None
        self._restore_engine()
        sizes = self._sizes()
        key = self.pet_settings.get('size') or spec.get('stage', 'default_size', default='S')
        self.size_key = key if key in sizes else next(iter(sizes))
        self.setFixedSize(*self._window_size(self.size_key))
        self._place_initial()
        self.view.load(QUrl(server.url('/web/pet.html')))
        if self.settings['show_panel']:
            QTimer.singleShot(400, lambda: self._set_panel(True))
        now = time.monotonic()
        self._last_tick = self._last_save = now
        self._tick = QTimer(self)
        self._tick.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._step)
        self._tick.start()
        self.show()

    # ------------------------------------------------------------------ engine + memory
    def _restore_engine(self):
        try:
            state = self.memory.load() or {}
            self.engine = self.spec.create_engine(os.path.dirname(self.memory.path), hour=local_hour())
            if state.get('engine'):
                self.engine.set_state(state['engine'], now=state.get('saved_at'), hour=local_hour())
                log.info('%s: memory restored (saved %s)', self.spec.id, time.ctime(state.get('saved_at', 0)))
        except Exception:
            log.exception('engine for %s failed; the pet stays in its idle clip', self.spec.id)
            self.engine = None

    def save(self):
        if self.engine:
            try:
                self.memory.save(self.engine.get_state())
            except Exception:
                log.exception('saving %s failed', self.spec.id)
        self.pet_settings['pos'] = [self.x(), self.y()]
        self.pet_settings['size'] = self.size_key
        self.settings.save()

    # ------------------------------------------------------------------ size + placement
    def _sizes(self):
        return self.spec.get('stage', 'sizes', default=None) or DEFAULT_SIZES

    def _frame(self):
        return {**DEFAULT_FRAME, **(self.spec.get('stage', 'frame', default=None) or {})}

    def pet_px(self):
        return int(self._sizes()[self.size_key])

    def _window_size(self, key):
        px, f = self._sizes()[key], self._frame()
        return int(round(px * f['width'])), int(round(px * f['height']))

    def _clamp_pos(self, x, y, w, h):
        scr = QGuiApplication.screenAt(QPoint(int(x + w / 2), int(y + h / 2))) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        feet = int(self._frame()['feet'] * self.pet_px() * 0.6)          # feet may sit on the taskbar edge
        return (max(g.left() - w // 4, min(int(x), g.right() - w + w // 4)),
                max(g.top() - h // 4, min(int(y), g.bottom() - h + feet)))

    def _place_initial(self):
        w, h = self.width(), self.height()
        pos = self.pet_settings.get('pos')
        if pos:
            x, y = pos
        else:
            g = QGuiApplication.primaryScreen().availableGeometry()
            x, y = g.right() - w - 40, g.bottom() - h + int(self._frame()['feet'] * self.pet_px() * 0.6)
        self.move(*self._clamp_pos(x, y, w, h))

    def set_size(self, key):
        if key not in self._sizes() or key == self.size_key:
            return
        g = self.geometry()
        cx, bottom = g.x() + g.width() / 2, g.y() + g.height()     # keep the feet where they are
        self.size_key = key
        w, h = self._window_size(key)
        self.setFixedSize(w, h)
        self.move(*self._clamp_pos(cx - w / 2, bottom - h, w, h))
        self.save()

    def set_variant(self, v):
        if v not in self.spec.variants() or v == self._variant():
            return
        self.pet_settings['variant'] = v
        self.settings.save()
        self.loaded = self._initialised = False
        self.view.reload()

    def _variant(self):
        v = self.pet_settings.get('variant')
        return v if v in self.spec.variants() else self.spec.get('model', 'default_variant')

    # ------------------------------------------------------------------ web page
    def _on_ready(self):
        if self._initialised:
            return
        self._initialised = True
        self.bridge.send({'type': 'init', 'pet_id': os.path.basename(self.spec.dir), 'manifest': self.spec.m,
                          'model': self.spec.variants()[self._variant()]})

    @Slot(str, 'QVariantMap')
    def _action(self, name, data):
        e = self.engine
        if (self.override or {}).get('freeze') and name in ('stroke', 'tap', 'poke', 'drag_start'):
            e = None                                     # review tool: a frozen engine must not learn from staged input
        if name == 'percept':
            self._js.update(dist=data.get('dist'), approach=float(data.get('approach') or 0.0),
                            speed=float(data.get('speed') or 0.0), jitter=float(data.get('jitter') or 0.0),
                            over=bool(data.get('over')), zone=data.get('zone'), pet_px=data.get('pet_px'))
        elif name == 'hover':
            self._hover = bool(data.get('over'))
            self._update_clickthrough()
        elif name == 'stroke':
            if e:
                e.event('pet', zone=str(data.get('zone') or 'body'), speed=float(data.get('speed') or 0.0))
        elif name in ('tap', 'poke'):
            if e:
                e.event(name, zone=str(data.get('zone') or 'body'))
        elif name == 'press':
            self._press_off = QCursor.pos() - self.pos()
        elif name == 'drag_start':
            self._drag = self._press_off or (QCursor.pos() - self.pos())
            self._update_clickthrough()
            if e:
                e.event('drag_start')
        elif name == 'drag_end':
            self._end_drag()
        elif name == 'menu':
            QTimer.singleShot(0, self.show_menu)
        elif name == 'loaded':
            self.loaded, self.load_info = True, data
            log.info('%s loaded: %s', self.spec.id, json.dumps(data))
        elif name == 'snapshot':
            if self.on_snapshot:
                self.on_snapshot(data)
        elif name == 'trace':
            if getattr(self, 'on_trace', None):
                self.on_trace(data)
        elif name == 'error':
            log.error('page: %s', data.get('msg'))

    def _end_drag(self):
        if self._drag is None:
            return
        self._drag = None
        self._drag_ended = True
        if self.engine:
            self.engine.event('drag_end')
        self._update_clickthrough()
        self.save()

    # ------------------------------------------------------------------ click-through (transparent pixels)
    def _update_clickthrough(self, force=False):
        want = not (self._hover or self._drag is not None or self._menu_open)
        if force or want != self._clickthrough:
            if set_click_through(self, want):
                self._clickthrough = want

    # ------------------------------------------------------------------ tick
    def _cursor_local(self):
        ov = self.override or {}
        if callable(ov.get('cursor_fn')):                  # review harness: a moving virtual cursor, per tick
            return ov['cursor_fn'](time.monotonic())
        if 'cursor' in ov:
            return ov['cursor']
        p = QCursor.pos() - self.pos()
        return {'x': p.x(), 'y': p.y()}

    def _step(self):
        now = time.monotonic()
        dt = min(0.1, max(0.001, now - self._last_tick))
        self._last_tick = now
        if self._drag is not None:
            if not (QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                self._end_drag()
            else:
                self.move(QCursor.pos() - self._drag)
        if now > self._ct_check:                        # Windows may drop the ex-style on show/raise: re-assert
            self._ct_check = now + 1.0
            self._update_clickthrough(force=True)
        if not self._initialised or not self.loaded:
            return
        ov = self.override or {}
        idle = idle_seconds()
        out, cmds, spawns, levels = self._out, [], [], {}
        try:
            if self.engine and not ov.get('freeze'):
                percepts = dict(cursor_dist=self._js['dist'], cursor_approach=self._js['approach'],
                                cursor_speed=self._js.get('speed', 0.0), cursor_jitter=self._js.get('jitter', 0.0),
                                cursor_over=self._js['over'], cursor_zone=self._js['zone'], pet_px=self.pet_px(),
                                idle_s=idle, hour=local_hour(), music=0.0,
                                held=self._drag is not None)
                out = normalize_output(self.engine.update(dt, percepts))
            if ov.get('out'):                                # review / trace tools: a forced output
                out = normalize_output({**out, **ov['out']})
                ov['out']['changed'] = False                   # start the forced clip once, then let it play
            self._out = out
            if self.panel is not None and self.panel.isVisible():
                self.panel.feed(out)
            cmds = self.sound.from_output(out)
            quiet = 8.0 if (self.settings['quieter_when_away'] and idle > 300) else 0.0
            for c in cmds:
                c['gain_db'] -= quiet
            spawns, levels = self.fx.step(dt, out, cmds)
            if ov.get('fx'):
                spawns += ov.pop('fx')
            if ov.get('levels'):
                levels.update(ov['levels'])
        except Exception:
            log.exception('tick failed for %s', self.spec.id)
        self.bridge.send(dict(type='frame', out=out, sounds=cmds, fx=spawns, levels=levels, cursor=self._cursor_local(),
                              volume=float(self.settings['volume']), muted=bool(self.settings['muted']),
                              drag_ended=self._drag_ended))
        self._drag_ended = False
        self.frames_sent += 1
        if now - self._last_save > 60:
            self._last_save = now
            self.save()

    # ------------------------------------------------------------------ menu
    def build_menu(self, m):
        out = self._out
        asleep = out.get('behaviour') == 'sleep'
        name = self.pet_settings.get('name') or self.spec.name
        head = m.addAction(f'{name}  -  {"asleep" if asleep else out.get("emotion", "")}')
        head.setEnabled(False)
        m.addSeparator()
        for item in self.spec.get('menu', default=[]) or []:
            when = item.get('when')
            if (when == 'awake' and asleep) or (when == 'asleep' and not asleep):
                continue
            a = m.addAction(item.get('label', item['id']))
            a.triggered.connect(lambda _=False, k=item['id']: self.engine and self.engine.event(k))
        m.addSeparator()
        sm = m.addMenu('Size')
        grp = QActionGroup(sm)
        for key, px in self._sizes().items():
            a = sm.addAction(SIZE_LABELS.get(key, key))
            a.setCheckable(True)
            a.setChecked(key == self.size_key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_size(k))
        variants = self.spec.variants()
        if len(variants) > 1:
            vm = m.addMenu('Look')
            vg = QActionGroup(vm)
            for v in variants:
                a = vm.addAction(v.replace('_', ' ').title())
                a.setCheckable(True)
                a.setChecked(v == self._variant())
                vg.addAction(a)
                a.triggered.connect(lambda _=False, k=v: self.set_variant(k))
        snd = m.addMenu('Sound')
        mute = snd.addAction('Mute')
        mute.setCheckable(True)
        mute.setChecked(bool(self.settings['muted']))
        mute.toggled.connect(lambda on: self._set_setting('muted', bool(on)))
        snd.addSeparator()
        sg = QActionGroup(snd)
        for label, v in VOLUMES:
            a = snd.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(float(self.settings['volume']) - v) < 0.05)
            sg.addAction(a)
            a.triggered.connect(lambda _=False, val=v: self._set_setting('volume', val))
        quiet = snd.addAction('Quieter when I am away')
        quiet.setCheckable(True)
        quiet.setChecked(bool(self.settings['quieter_when_away']))
        quiet.toggled.connect(lambda on: self._set_setting('quieter_when_away', bool(on)))
        panel = m.addAction('Mood panel')
        panel.setCheckable(True)
        panel.setChecked(self.panel is not None and self.panel.isVisible())
        panel.toggled.connect(self._set_panel)
        m.addSeparator()
        hide = m.addAction(f'Hide {name}')
        hide.triggered.connect(self.hide)
        q = m.addAction(f'Quit {APP_NAME}')
        q.triggered.connect(QApplication.quit)
        return m

    def show_menu(self):
        if self.engine:
            self.engine.event('menu_open')               # a learned cue: the menu often means food
        self._menu_open = True
        self._update_clickthrough()
        try:
            self.build_menu(QMenu(self)).exec(QCursor.pos())
        finally:
            self._menu_open = False
            self._update_clickthrough()

    def _set_setting(self, k, v):
        self.settings[k] = v
        self.settings.save()

    # ------------------------------------------------------------------ mood panel (separate window)
    def _set_panel(self, on):
        self._set_setting('show_panel', bool(on))
        if on:
            if self.panel is None:
                self.panel = MoodPanel(self.pet_settings.get('name') or self.spec.name, self.spec.get('panel', default={}),
                                       on_moved=self._panel_moved, on_closed=lambda: self._set_setting('show_panel', False))
                pos = self.settings['panel_pos']
                if pos:
                    self.panel.move(self.panel.clamp(QPoint(int(pos[0]), int(pos[1]))))
                else:
                    self.panel.place_near(self.geometry())
            self.panel.feed(self._out)
            self.panel.show()
            self.panel.raise_()
        elif self.panel is not None:
            self.panel.hide()

    def _panel_moved(self, pos):
        self._set_setting('panel_pos', [pos.x(), pos.y()])

    def hideEvent(self, ev):
        if self.panel is not None:
            self.panel.hide()
        super().hideEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.panel is not None and self.settings['show_panel']:
            self.panel.show()

    def snapshot(self, tag):
        self.bridge.send({'type': 'snapshot', 'tag': tag})

    def closeEvent(self, ev):
        self.save()
        if self.panel is not None:
            self.panel.close()
        ev.accept()


def make_tray(app, windows):
    icon_path = next((w.spec.path(w.spec.m['icon']) for w in windows
                      if w.spec.m.get('icon') and os.path.isfile(w.spec.path(w.spec.m['icon']))), None)
    tray = QSystemTrayIcon(QIcon(icon_path) if icon_path else app.style().standardIcon(
        app.style().StandardPixmap.SP_ComputerIcon), app)
    tray.setToolTip(f'{APP_NAME} {__version__}')
    menu = QMenu()

    def rebuild():
        menu.clear()
        for w in windows:
            sub = menu.addMenu(w.pet_settings.get('name') or w.spec.name) if len(windows) > 1 else menu
            vis = sub.addAction('Show' if not w.isVisible() else 'Bring to front')
            vis.triggered.connect(lambda _=False, ww=w: (ww.show(), ww.raise_()))
            if len(windows) == 1:
                sub.addSeparator()
                w.build_menu(sub)
        if len(windows) > 1:
            menu.addSeparator()
            menu.addAction(f'Quit {APP_NAME}').triggered.connect(QApplication.quit)

    menu.aboutToShow.connect(rebuild)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: [(w.show(), w.raise_()) for w in windows]
                           if r == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    return tray


def setup_logging():
    os.makedirs(paths.data_dir(), exist_ok=True)
    logging.basicConfig(filename=paths.log_path(), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s', force=True)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    selftest = '--selftest' in argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    setup_logging()
    # one running copy per data folder: two copies would fight over the same memory files
    os.makedirs(paths.data_dir(), exist_ok=True)
    lock = QLockFile(os.path.join(paths.data_dir(), 'app.lock'))
    lock.setStaleLockTime(0)                        # a crashed copy's lock is detected by PID, not by age
    if not selftest and not lock.tryLock(200):
        log.info('%s is already running (lock held) - this copy exits', APP_NAME)
        return 0
    log.info('%s %s starting (data %s)', APP_NAME, __version__, paths.data_dir())
    pets = discover()
    if not pets:
        log.error('no valid pet plugins in %s', paths.PETS_DIR)
        return 2
    server = AssetServer(paths.ROOT).start()
    settings = Settings()
    windows = [PetWindow(s, server, settings) for s in pets if settings.pet(s.id).get('enabled', True)]
    tray = make_tray(app, windows)
    result = {}
    if selftest:
        def check():
            ok = all(w.loaded and w.frames_sent > 10 and w.engine is not None for w in windows)
            result['ok'] = ok
            log.info('selftest %s: %s', 'OK' if ok else 'FAILED',
                     [(w.spec.id, w.loaded, w.frames_sent, w.load_info.get('rig')) for w in windows])
            if sys.stdout:
                print('SELFTEST', 'OK' if ok else 'FAILED', [(w.spec.id, w.loaded, w.frames_sent, w.load_info) for w in windows])
            app.quit()
        QTimer.singleShot(int(os.environ.get('DP3D_SELFTEST_MS', '9000')), check)
    code = app.exec()
    for w in windows:
        w.save()
    tray.hide()
    server.stop()
    if selftest:
        return 0 if result.get('ok') else 3
    return code


if __name__ == '__main__':
    raise SystemExit(main())
