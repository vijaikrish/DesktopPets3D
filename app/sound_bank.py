"""Turns engine output into concrete sound files to play (the browser side plays them with WebAudio).

Driven by the pet's sounds/sound_bank.json (format written by SunConure3D/sounds/build_sound_bank.py):
  categories      name -> {jaw_deg, files: [{file, seconds, envelope_60fps}]}
  clip_events     'clip:event' or '*:event' -> {sound: 'cat' | 'cat|cat2' | '' (silent), gain_db, lip_sync}
  clip_sounds     clip -> [[t_s, 'cat', gain_db], ...]   for clips without baked events
  engine_tokens   engine sound token -> category
and the plugin's pet.json "sounds" section, which may override / extend the bank:
  vocal_categories, sleep_categories, mouth_categories, quiet_clips, min_jaw_deg, jaw_deg{cat: deg},
  engine_tokens{...}, clip_events{...}, clip_sounds{...}   (a sound of '' silences a token / event)

Rules
- One vocal call at a time (birds don't talk over themselves), random file without immediate repeats, small random
  pitch / level variation (more when aroused), only quiet sounds while asleep.
- A sound that comes out of the mouth (vocal categories + mouth_categories such as beak grinding / clicks) must be SEEN:
  either the clip's own bake opens the beak at that moment (clip event with lip_sync false), or the jaw follows the
  sound's loudness envelope, opening at least min_jaw_deg. (Vijai, 2026-10-29: "whenever he speaks I would like to see
  the beaks moving ... or remove the sound at that time".)
- While a quiet clip plays (beak busy or hidden: being scratched, asleep, eating, preening) the engine's spontaneous
  mouth sounds wait up to HOLD_S for the next clip and are dropped if it does not come. Baked clip events always play:
  they were made for that animation.
"""
import json
import os
import random
import time

DEFAULT_VOCAL = ('contact_call', 'squawk', 'alarm', 'excited', 'chirp', 'chatter', 'speech', 'whistle', 'growl')
DEFAULT_SLEEP_OK = ('grind', 'sigh')
DEFAULT_MOUTH_EXTRA = ('grind', 'click')
HOLD_S = 0.6


class SoundBank:
    def __init__(self, spec):
        self.spec = spec
        rel = spec.get('sounds', 'bank')
        self.ok = bool(rel) and os.path.exists(spec.path(rel))
        self.bank = {}
        if self.ok:
            with open(spec.path(rel), encoding='utf-8') as f:
                self.bank = json.load(f)
        self.base = os.path.dirname(rel) if rel else ''
        self.cats = self.bank.get('categories', {})
        s = spec.get('sounds', default={}) or {}
        self.events = {**self.bank.get('clip_events', {}), **(s.get('clip_events') or {})}
        self.clip_sounds = {**self.bank.get('clip_sounds', {}), **(s.get('clip_sounds') or {})}
        self.tokens = {**self.bank.get('engine_tokens', {}), **(s.get('engine_tokens') or {})}   # '' = silent
        self.vocal = set(s.get('vocal_categories', DEFAULT_VOCAL))
        self.sleep_ok = set(s.get('sleep_categories', DEFAULT_SLEEP_OK))
        self.mouth = self.vocal | set(s.get('mouth_categories', DEFAULT_MOUTH_EXTRA))
        self.quiet_clips = set(s.get('quiet_clips', ()))
        self.min_jaw = float(s.get('min_jaw_deg', 0.0))
        self.jaw_deg = dict(s.get('jaw_deg') or {})
        self._last = {}
        self._vocal_until = 0.0
        self._clip = None
        self._clip_t = 0.0
        self._fired = set()
        self._pending = []                  # [(deadline, category expression)] mouth sounds waiting for the beak
        self.stats = dict(played=0, held=0, dropped=0)

    # ---------------------------------------------------------------- helpers
    def jaw_for(self, cat):
        """Degrees the jaw opens at the loudest point of a lip-synced sound of this category."""
        if cat in self.jaw_deg:                       # the plugin's explicit value wins
            return float(self.jaw_deg[cat])
        deg = float(self.cats.get(cat, {}).get('jaw_deg', 0))
        return max(deg, self.min_jaw) if cat in self.mouth else deg

    def _cats(self, expr):
        return [c for c in (expr or '').split('|') if c in self.cats and self.cats[c].get('files')]

    def is_mouth(self, expr):
        cats = self._cats(expr)
        return bool(cats) and any(c in self.mouth for c in cats)

    # ---------------------------------------------------------------- selection
    def _pick(self, expr, gain_db=0.0, lip=True, arousal=0.5, asleep=False, now=None):
        if not self.ok or not expr:
            return None
        cats = self._cats(expr)
        if not cats:
            return None
        cat = random.choice(cats)
        if asleep and cat not in self.sleep_ok:
            return None
        now = time.monotonic() if now is None else now
        vocal = cat in self.vocal
        if vocal and now < self._vocal_until:
            return None
        files = self.cats[cat]['files']
        choices = [f for f in files if f['file'] != self._last.get(cat)] or files
        f = random.choice(choices)
        self._last[cat] = f['file']
        jitter = 0.03 + 0.02 * max(0.0, arousal - 0.5)
        rate = 1.0 + random.uniform(-jitter, jitter)
        dur = float(f.get('seconds', 0.5)) / rate
        if vocal:
            self._vocal_until = now + dur + 0.08
        jaw = self.jaw_for(cat) if lip else 0.0
        self.stats['played'] += 1
        return dict(url=self.spec.url(f'{self.base}/{f["file"]}'.lstrip('/')), category=cat,
                    gain_db=float(gain_db) + 3.0 * (arousal - 0.5) + random.uniform(-1.0, 1.0), rate=rate, dur=dur,
                    jaw_deg=jaw, env=f.get('envelope_60fps') if jaw > 0 else None, mouth=cat in self.mouth)

    # ---------------------------------------------------------------- per tick
    def from_output(self, out, now=None):
        """All sounds to start this tick, from engine tokens, clip events and the clip schedule."""
        now = time.monotonic() if now is None else now
        cmds = []
        asleep = out.get('behaviour') == 'sleep'
        arousal = float((out.get('affect') or {}).get('arousal', 0.5))
        quiet = out.get('clip') in self.quiet_clips
        for tok in out.get('sounds') or []:
            expr = self.tokens.get(tok, tok)
            if self.is_mouth(expr):
                self._pending.append((now + HOLD_S, expr))     # played below as soon as the beak is free
                continue
            c = self._pick(expr, arousal=arousal, asleep=asleep, now=now)
            if c:
                cmds.append(c)
        keep = []
        for deadline, expr in self._pending:
            if not quiet:
                c = self._pick(expr, arousal=arousal, asleep=asleep, now=now)
                if c:
                    cmds.append(c)
            elif now < deadline:
                keep.append((deadline, expr))
                self.stats['held'] += 1
            else:
                self.stats['dropped'] += 1
        self._pending = keep
        for clip, ev in out.get('clip_events') or []:
            m = self.events.get(f'{clip}:{ev}') or self.events.get(f'*:{ev}')
            if m and m.get('sound'):
                c = self._pick(m['sound'], m.get('gain_db', 0), m.get('lip_sync', True), arousal, asleep, now)
                if c:
                    if m.get('mouth') is False:            # beak contact (wiping on the perch): the head motion shows it
                        c['mouth'] = False
                    cmds.append(c)
        cmds += self._schedule(out, arousal, asleep, now)
        return cmds

    def _schedule(self, out, arousal, asleep, now):
        clip, t = out.get('clip'), float(out.get('clip_time') or 0.0)
        sched = self.clip_sounds.get(clip, [])
        if clip != self._clip or out.get('changed'):
            self._clip, self._fired = clip, set()
        elif t + 1e-6 < self._clip_t:                  # wrapped: a loop restart, or a hover loop back to 'start'
            base = float((out.get('hold') or {}).get('start', 0.0)) if out.get('hold') else 0.0
            base = base if t >= base - 0.05 else 0.0
            self._fired = {k for k, (ts, _, _) in enumerate(sched) if ts < base - 1e-6}
        self._clip_t = t
        cmds = []
        for k, (ts, expr, gain) in enumerate(sched):
            if k not in self._fired and t >= ts:
                self._fired.add(k)
                c = self._pick(expr, gain, True, arousal, asleep, now)
                if c:
                    cmds.append(c)
        return cmds
