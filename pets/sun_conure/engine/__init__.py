"""Sun-conure plugin adapter: translates the core's species-neutral percepts/events into ConureMind's own units.

Core percepts are screen pixels for the bird as it is drawn right now (Small/Medium/Large). ConureMind's distance and
speed constants were tuned for a bird about REF_PX pixels tall, so the adapter rescales by REF_PX / pet_px: the same
hand gesture means the same thing to the bird at every size.
"""
import logging

from .conure_mind import ConureMind

log = logging.getLogger(__name__)
REF_PX = 160.0          # bird height (px) the v2 constants (near = exp(-d/250), stroke speed bands) were tuned for


def create_engine(ctx):
    # ConureMind's native clip table uses {dur, loop, events}; the shared parser already supplies that shape.
    return SunConureAdapter(ConureMind(ctx.clips, seed=ctx.seed, hour=ctx.hour), ctx.options)


class SunConureAdapter:
    def __init__(self, mind, options=None):
        self.mind = mind
        self.k = 1.0
        # Starting temperament of a NEW bird (saved memory replaces it): hand-tame, expects scratches from the cursor.
        for key, v in ((options or {}).get('start') or {}).items():
            if key in ('bond', 'exp_pet', 'exp_poke', 'touch', 'social', 'boredom'):
                setattr(mind, key, float(v))

    def event(self, name, **kw):
        if name == 'pet' and kw.get('speed') is not None:
            kw['speed'] = float(kw['speed']) * self.k
        try:
            self.mind.event(name, **kw)
        except (KeyError, ValueError, TypeError):
            log.debug('event %s ignored', name)      # another pet's menu/event is irrelevant to this engine

    def update(self, dt, percepts):
        p = percepts or {}
        px = p.get('pet_px')
        if px:
            self.k = REF_PX / max(40.0, float(px))
        d = p.get('cursor_dist')
        mp = dict(idle_s=float(p.get('idle_s', 0.0)), hour=float(p.get('hour', 12.0)),
                  music=float(p.get('music', 0.0)), held=bool(p.get('held', False)),
                  cursor_dist=None if d is None else float(d) * self.k,
                  # ConureMind reads cursor_speed as 'how fast the hand comes AT me' (looming / startle), so it gets the
                  # approach speed, not the raw speed: moving the mouse past the bird is not a threat.
                  cursor_speed=max(0.0, float(p.get('cursor_approach', 0.0))) * self.k,
                  # v4 appraisal inputs: raw path speed (size-normalised), jitter (Hz, size-free), over / zone
                  cursor_move=max(0.0, float(p.get('cursor_speed', 0.0) or 0.0)) * self.k,
                  cursor_jitter=float(p.get('cursor_jitter', 0.0) or 0.0),
                  cursor_over=bool(p.get('cursor_over', False)), cursor_zone=p.get('cursor_zone'))
        return self.mind.update(dt, mp)

    def get_state(self):
        return self.mind.get_state()

    def set_state(self, state, now=None, hour=None):
        return self.mind.set_state(state, now=now, hour=hour)

    def info(self):
        return dict(name='ConureMind', version='v5 CTRNN + appraisal layer + comfort/provocation neuromodulation + sleep debt', emotions=len(self.mind.E),
                    behaviours=len(self.mind.B))
