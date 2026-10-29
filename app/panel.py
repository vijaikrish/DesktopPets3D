"""Mood panel: a small, separate, draggable window that shows what the pet feels and needs right now.

Its own top-level window (not drawn inside the pet), so it can be put anywhere on the screen and stays readable: an
opaque dark card, fixed row order (rows never jump around), values smoothed over ~0.5 s, plain-language labels.
Everything species-specific comes from the plugin's pet.json "panel" block:

  "panel": {
    "meters":   [{"label": "Hunger", "from": "drives.hunger", "full": 0.6, "color": "#E8A33C",
                  "levels": [[0.25, "Full"], [0.55, "Peckish"], [1.0, "Hungry"]]}, ...],
    "emotions": [["happy", "Happy", "#F2B705"], ...],          # [engine name, label, bar colour]
    "behaviours": {"enjoy_petting": "enjoying a head scratch", ...},
    "emotion_words": {"neutral": "Calm", ...}
  }
Drawn with QPainter (no second web view: a few hundred kB of RAM instead of ~100 MB).
"""
import math

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

W = 280            # logical px; Qt scales for high-DPI screens
PAD = 14
BG = QColor(24, 27, 34, 246)
EDGE = QColor(70, 76, 90)
TEXT = QColor(236, 238, 242)
MUTED = QColor(160, 168, 182)
TRACK = QColor(54, 59, 72)
DEFAULT_EMOTIONS = [['happy', 'Happy', '#F2B705'], ['playful', 'Playful', '#F28C28'],
                    ['affectionate', 'Affectionate', '#E86A9E'], ['content', 'Relaxed', '#5DBB63'],
                    ['curious', 'Curious', '#4C9BE8'], ['sleepy', 'Sleepy', '#8E7CF0'],
                    ['frustrated', 'Frustrated', '#D9822B'], ['angry', 'Angry', '#E5484D'],
                    ['afraid', 'Scared', '#9AA4B2'], ['sad', 'Sad', '#6C7A99']]


def _get(d, path, default=0.0):
    for k in path.split('.'):
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    try:
        return float(d)
    except (TypeError, ValueError):
        return default


class MoodPanel(QWidget):
    def __init__(self, title, cfg=None, on_moved=None, on_closed=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        mac_attr = getattr(Qt.WidgetAttribute, 'WA_MacAlwaysShowToolWindow', None)
        if mac_attr is not None:
            self.setAttribute(mac_attr, True)          # macOS hides tool windows of inactive apps otherwise
        self.setWindowTitle(f'{title} - mood')
        self.title = title
        cfg = cfg or {}
        self.meters = cfg.get('meters') or []
        self.emotions = cfg.get('emotions') or DEFAULT_EMOTIONS
        self.behaviours = cfg.get('behaviours') or {}
        self.words = cfg.get('emotion_words') or {}
        self.on_moved, self.on_closed = on_moved, on_closed
        self._out = None
        self._val = {}                                 # smoothed values
        self._drag = None
        self._close_rect = QRectF()
        self.f_title = QFont(self.font()); self.f_title.setPointSizeF(11.5); self.f_title.setBold(True)
        self.f_big = QFont(self.font()); self.f_big.setPointSizeF(10.5); self.f_big.setBold(True)
        self.f_row = QFont(self.font()); self.f_row.setPointSizeF(9.5)
        self.f_small = QFont(self.font()); self.f_small.setPointSizeF(8.5)
        self.f_head = QFont(self.font()); self.f_head.setPointSizeF(8.0); self.f_head.setBold(True)
        self.f_head.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
        self.setFixedSize(W, self._height())
        self._timer = QTimer(self)
        self._timer.setInterval(200)                   # 5 Hz is plenty for reading
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ data
    def feed(self, out):
        self._out = out

    def _target(self):
        out = self._out or {}
        t = {}
        for i, m in enumerate(self.meters):
            t[f'm{i}'] = max(0.0, min(1.0, _get(out, m['from']) / float(m.get('full', 1.0))))
        emo = out.get('emotions') or {}
        for name, *_ in self.emotions:
            t[f'e:{name}'] = max(0.0, min(1.0, float(emo.get(name, 0.0))))
        t['bond'] = _get(out, 'drives.bond')
        t['mood'] = _get(out, 'mood.valence')
        return t

    def _tick(self):
        if not self.isVisible() or self._out is None:
            return
        k = 1 - math.exp(-0.2 / 0.45)
        for key, v in self._target().items():
            self._val[key] = v if key not in self._val else self._val[key] + (v - self._val[key]) * k
        self.update()

    def snapshot_values(self):
        """For tests: the smoothed values currently drawn."""
        return dict(self._val)

    # ------------------------------------------------------------------ layout
    def _height(self):
        h = PAD + 22 + 22 + 10                                  # title, status, gap
        h += 16 + len(self.meters) * 50                          # NEEDS header + meters (label, bar, level)
        h += 8 + 16 + len(self.emotions) * 19                    # FEELINGS header + rows
        h += 10 + 18 + PAD                                      # footer
        return h

    def place_near(self, rect):
        """First show: put the panel beside the pet's window, on the side with more room."""
        scr = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        x = rect.left() - self.width() - 8 if rect.left() - g.left() > g.right() - rect.right() else rect.right() + 8
        y = max(g.top() + 8, min(rect.bottom() - self.height(), g.bottom() - self.height() - 8))
        self.move(self.clamp(QPoint(int(x), int(y))))

    def clamp(self, p):
        scr = QGuiApplication.screenAt(p + QPoint(self.width() // 2, 20)) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        return QPoint(max(g.left(), min(p.x(), g.right() - self.width())),
                      max(g.top(), min(p.y(), g.bottom() - self.height())))

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, BG)
        p.setPen(QPen(EDGE, 1))
        p.drawPath(path)
        out = self._out or {}
        v = self._val
        x0, x1 = PAD, W - PAD
        y = PAD
        # title + close
        p.setFont(self.f_title); p.setPen(TEXT)
        p.drawText(QRectF(x0, y, x1 - x0 - 24, 22), Qt.AlignmentFlag.AlignVCenter, self.title)
        self._close_rect = QRectF(x1 - 20, y + 1, 20, 20)
        p.setPen(QPen(MUTED, 1.6))
        c = self._close_rect.center()
        for dx, dy in ((-5, -5), (-5, 5)):
            p.drawLine(int(c.x() + dx), int(c.y() + dy), int(c.x() - dx), int(c.y() - dy))
        y += 22
        # status: mood word + what it is doing
        emo = out.get('emotion') or 'neutral'
        label = {n: l for n, l, *_ in self.emotions}.get(emo) or self.words.get(emo) or emo.replace('_', ' ').title()
        col = {n: (rest[0] if rest else '#F2B705') for n, _l, *rest in self.emotions}.get(emo, '#C8CED8')
        beh = out.get('behaviour') or ''
        doing = self.behaviours.get(beh) or beh.replace('_', ' ')
        p.setFont(self.f_big); p.setPen(QColor(col))
        fm = QFontMetrics(self.f_big)
        p.drawText(QRectF(x0, y, x1 - x0, 20), Qt.AlignmentFlag.AlignVCenter, label)
        p.setFont(self.f_row); p.setPen(MUTED)
        lw = fm.horizontalAdvance(label) + 8
        doing = QFontMetrics(self.f_row).elidedText(f'·  {doing}', Qt.TextElideMode.ElideRight, int(x1 - x0 - lw))
        p.drawText(QRectF(x0 + lw, y, x1 - x0 - lw, 20), Qt.AlignmentFlag.AlignVCenter, doing)
        y += 22 + 10
        # needs (meters)
        y = self._header(p, 'NEEDS', x0, x1, y)
        for i, m in enumerate(self.meters):
            val = v.get(f'm{i}', 0.0)
            level = next((txt for lim, txt in m.get('levels', []) if val <= lim), '')
            p.setFont(self.f_row); p.setPen(TEXT)
            p.drawText(QRectF(x0, y, x1 - x0 - 50, 18), Qt.AlignmentFlag.AlignVCenter, m.get('label', ''))
            p.drawText(QRectF(x1 - 50, y, 50, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       f'{round(100 * val)} %')
            self._bar(p, x0, y + 20, x1 - x0, 9, val, QColor(m.get('color', '#E8A33C')))
            p.setFont(self.f_small); p.setPen(MUTED)
            p.drawText(QRectF(x0, y + 31, x1 - x0, 15), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(self.f_small).elidedText(level, Qt.TextElideMode.ElideRight, int(x1 - x0)))
            y += 50
        y += 8
        # feelings
        y = self._header(p, 'FEELINGS', x0, x1, y)
        lab_w = 92
        for name, lab, *rest in self.emotions:
            val = v.get(f'e:{name}', 0.0)
            p.setFont(self.f_row)
            p.setPen(TEXT if val > 0.25 else MUTED)
            p.drawText(QRectF(x0, y, lab_w, 17), Qt.AlignmentFlag.AlignVCenter, lab)
            self._bar(p, x0 + lab_w, y + 6, x1 - x0 - lab_w, 6, val, QColor(rest[0] if rest else '#F2B705'))
            y += 19
        y += 10
        # footer
        p.setFont(self.f_small); p.setPen(MUTED)
        mood = v.get('mood', 0.0)
        p.drawText(QRectF(x0, y, x1 - x0, 18), Qt.AlignmentFlag.AlignVCenter,
                   f'Bond {round(100 * v.get("bond", 0.0))} %   ·   Mood {"+" if mood >= 0 else ""}{mood:.2f}')
        p.drawText(QRectF(x0, y, x1 - x0, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   'drag to move')
        p.end()

    def _header(self, p, text, x0, x1, y):
        p.setFont(self.f_head); p.setPen(MUTED)
        p.drawText(QRectF(x0, y, x1 - x0, 14), Qt.AlignmentFlag.AlignVCenter, text)
        p.setPen(QPen(QColor(60, 65, 78), 1))
        tw = QFontMetrics(self.f_head).horizontalAdvance(text) + 8
        p.drawLine(int(x0 + tw), int(y + 7), int(x1), int(y + 7))
        return y + 16

    @staticmethod
    def _bar(p, x, y, w, h, val, col):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(TRACK)
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        if val > 0.005:
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, y, max(h, w * min(1.0, val)), h), h / 2, h / 2)

    # ------------------------------------------------------------------ mouse: drag anywhere, x closes
    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        if self._close_rect.contains(ev.position()):
            self.hide()
            if self.on_closed:
                self.on_closed()
            return
        self._drag = ev.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            self.move(self.clamp(ev.globalPosition().toPoint() - self._drag))

    def mouseReleaseEvent(self, _ev):
        if self._drag is not None:
            self._drag = None
            if self.on_moved:
                self.on_moved(self.pos())
