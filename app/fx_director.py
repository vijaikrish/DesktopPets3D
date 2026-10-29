"""2D effect director: decides WHICH effects to spawn; the browser draws them (web/js/fx.js).

Everything comes from the pet's pet.json "fx" block, so every pet can have its own look:
  tokens   engine fx token        -> [effect, ...]           e.g. "anger": smoke puffs + anger mark
  ambient  [{when, kind, rate_hz}]                           Poisson spawns while a condition holds
  levels   {effect: emotion}                                  continuous effects (sad rain cloud) follow an emotion
  clips    clip -> [{kind, rate_hz} | {kind, at: t_s}]        e.g. leaves shaken off the branch by a hop
  sounds   sound category -> [effect, ...]                    e.g. notes when it sings / whistles
  petting  {good: [...], bad: [...], meh: [...]}              feedback on each stroke / tap (optional)
  cooldown_s {kind: s}                                        minimum gap between two spawns of one kind (no spam
                                                              when the engine emits a token on every stroke)
An effect is {kind, anchor, count, chance, size}; anchor None = the kind's default in web/js/fx.js (heart above the
head, note at the beak, tear at an eye, leaves from the top edge...). Spawns are random (Poisson), never on a timer.
`when`: {emotion, above} | {behaviour} | {behaviour_in: [...]} | {drive, above} | {clip_in: [...]}.
"""
import random


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


class FxDirector:
    def __init__(self, spec):
        self.rules = spec.get('fx', default={}) or {}
        self._clip = None
        self._clip_t = 0.0
        self._fired = set()
        self.cooldown = dict(self.rules.get('cooldown_s') or {})
        self._last = {}
        self.t = 0.0

    def _cond(self, when, out):
        e = out.get('emotions') or {}
        if 'emotion' in when:
            v = float(e.get(when['emotion'], 0.0))
            a = float(when.get('above', 0.5))
            return (0.5 + 0.5 * _clamp((v - a) / max(1e-6, 1 - a))) if v > a else 0.0
        if 'drive' in when:
            v = float((out.get('drives') or {}).get(when['drive'], 0.0))
            return 1.0 if v > float(when.get('above', 0.5)) else 0.0
        if 'behaviour' in when:
            return 1.0 if out.get('behaviour') == when['behaviour'] else 0.0
        if 'behaviour_in' in when:
            return 1.0 if out.get('behaviour') in when['behaviour_in'] else 0.0
        if 'clip_in' in when:
            return 1.0 if out.get('clip') in when['clip_in'] else 0.0
        return 0.0

    def _emit(self, lst, effects):
        for fx in effects or []:
            kind = fx['kind']
            if self.t - self._last.get(kind, -1e9) < float(self.cooldown.get(kind, 0.0)):
                continue
            if random.random() <= float(fx.get('chance', 1.0)):
                self._last[kind] = self.t
                lst.append(dict(kind=kind, anchor=fx.get('anchor'), count=int(fx.get('count', 1)),
                                size=float(fx.get('size', 1.0))))

    def step(self, dt, out, sounds_started=()):
        """-> (spawns, levels) for this tick."""
        r = self.rules
        self.t += dt
        spawns = []
        for tok in out.get('fx') or []:
            self._emit(spawns, (r.get('tokens') or {}).get(tok))
        for rule in r.get('ambient') or []:
            k = self._cond(rule.get('when', {}), out)
            if k > 0 and random.random() < float(rule.get('rate_hz', 0.5)) * k * dt:
                self._emit(spawns, [rule])
        clip, t = out.get('clip'), float(out.get('clip_time') or 0.0)
        if clip != self._clip or out.get('changed') or t + 1e-6 < self._clip_t:
            self._clip, self._fired = clip, set()
        self._clip_t = t
        for k, rule in enumerate((r.get('clips') or {}).get(clip, [])):
            if 'at' in rule:
                if k not in self._fired and t >= float(rule['at']):
                    self._fired.add(k)
                    self._emit(spawns, [rule])
            elif random.random() < float(rule.get('rate_hz', 1.0)) * dt:
                self._emit(spawns, [rule])
        for s in sounds_started:
            self._emit(spawns, (r.get('sounds') or {}).get(s.get('category')))
        pet = out.get('petting')
        if pet:
            q = float(pet.get('quality', 0.0))
            self._emit(spawns, (r.get('petting') or {}).get('good' if q > 0.35 else 'bad' if q < -0.35 else 'meh'))
        levels = {}
        for fx, emo in (r.get('levels') or {}).items():
            levels[fx] = float((out.get('emotions') or {}).get(emo, 0.0))
        return spawns, levels
