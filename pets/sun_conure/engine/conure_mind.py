"""ConureMind - a neural emotion engine for the 3D sun conure (numpy only, no Qt, no Blender).

Layers (all continuous-time; nothing is driven by 'every N seconds' timers):
  v5 (2026-10-29): SLEEP DEBT (kept awake -> grumpy; only sleep repays it, treats do not), the bird's own
  circadian clock (it sleeps late in the evening even under the lamp), 'fly' (take-off, hover, landing), and the
  head scratch ends as soon as the hand leaves the head.
  1. Senses     percepts from the app (cursor distance/speed, user idle time, clock, music, drag) + discrete
                events (pet, poke, feed_sunflower, feed_millet, menu_open, play, fly, ...; talk / lights_off /
                music_on are still understood but no longer sent by the 0.4 app).
  2. Body       artificial biochemistry: hunger, sleep pressure S (Borbely), social need, boredom, grooming
                need, stress (corticosterone); first-order ODEs + light/circadian input.
  3. Learning   Rescorla-Wagner delta rule (a single-layer net): time-of-day -> food, right-click menu -> food,
                cursor approach -> petting / poking; startle habituation; bond (trust) with the user.
  4. Emotions   17 leaky-integrator sigmoid neurons (a CTRNN) wired by genome.py: inputs from body/senses/
                learning/mood, self-excitation (persistence), mutual inhibition/excitation, OU noise
                (spontaneous drift). Their activations place the bird in core-affect space (valence, arousal,
                stance); mood is the slow running mean of that point and feeds back as cognitive bias.
  5. Behaviour  ~28 behaviour units: motivation = weighted emotions + features + Lorenz urge - boredom with
                itself (level of interest) + persistence; chosen by softmax sampling (temperature rises with
                arousal) whenever a clip ends; priority behaviours (startle, fear, threat, greet, petting)
                interrupt. Each behaviour picks one of its baked clips (emotion bands, no repeats).
  6. Expression continuous face/gaze/sound/fx outputs for the 3D app layered on the playing clip
                (pupil pinning, crest, fluff, lid droop, Poisson blinks/saccades/chirps).

Typical use in the app (any frame rate):
    mind = ConureMind(clip_table_from_manifest('export/animations.json'), seed=None)
    mind.event('feed_sunflower')                       # from the right-click menu
    out = mind.update(dt, dict(cursor_dist=420, cursor_speed=80, idle_s=3, hour=14.5))
    out['clip'], out['clip_time'], out['speed'], out['changed'], out['crossfade'], out['face'], out['sounds']
    out['follow']   -> how the body follows the cursor (approach / watch / avoid / confront / turn_away)
    mind.event('pet', zone='head', speed=180)          # while stroking, a few times per second
    out['petting']  -> how that stroke felt (quality -1..1) so the app can show hearts or a warning

v2 (touch & the hand): a need for physical affection (touch_need) that grows while awake; petting quality by body
zone / stroke speed / over-stimulation / mood; the approaching hand (cursor) is learned as a good or bad sign;
'neglect' builds when needs stay unmet while the user is at the PC. Cursor coming close -> excited (good hand),
sad (neglected) or angry / afraid (bad hand).

v4 (DesktopPets3D, 2026-10-29): an APPRAISAL layer between the cursor and the network judges what the hand is DOING
(gentle movement -> happy/playful, resting close -> curious, resting on the head -> relaxed, frantic scrubbing right on
the bird -> mildly irritated, capped); a COMFORT neuromodulator (petting, head touch, food) shortens the decay time
constant of anger/fear/frustration; only clicks (tap / poke) provoke real anger; strokes are never unpleasant (too
much = satiation). Menu events 'pet_session' (hand-free head scratch) and 'poke_once'.
"""
import ast
import json
import math
import os
import re
import time

import numpy as np

try:
    from . import genome as G
except ImportError:                       # run as a plain script / from tools
    import genome as G

H_MAX = 0.25                              # internal integration step (s)
TRACE_TAU = dict(petting=3.0, poke=8.0, sudden=0.5, reward_sun=120.0, reward_mil=90.0, talk=12.0, play_inv=25.0,
                 reunion=25.0, just_woke=45.0, novelty_ev=6.0, menu=10.0, held=1.0, pet_bad=6.0,
                 irritate=4.0, comfort=20.0)
RESPONSE_EVENTS = ('pet', 'feed_sunflower', 'feed_millet', 'talk', 'play', 'pet_session', 'fly')
CALM_BEHAVIOURS = ('rest', 'doze', 'sleep', 'groom', 'stretch', 'enjoy_petting', 'affection', 'watch_user', 'look_around',
                   'bored_idle', 'mope', 'solicit_petting')


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def smoothstep(x, a, b):
    t = clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def bio_night(hour, ramps=(21.0, 22.5, 6.0, 7.5)):
    """The bird's internal clock: 0 by day, 1 at night (independent of the room light)."""
    h = hour % 24.0
    a, b, c, d = ramps
    return max(smoothstep(h, a, b), 1.0 - smoothstep(h, c, d) if h < 12.0 else 0.0)


def light_level(hour, lights_off=False, present=0.0):
    """Light the bird sees 0..1: dawn 07:00-08:00, dusk 21:00-22:00; while its person is at the PC in the
    evening the room lamp stays on (0.85) until they leave the PC (or an optional 'lights_off' event) - indoor birds
    sleep when it gets dark. Under the lamp the bird's own clock (bio_night) still makes it sleepy from ~21:30."""
    if lights_off:
        return 0.0
    h = hour % 24.0
    natural = clamp(h - 7.0) * clamp(22.0 - h)
    if present > 0.3 and h >= 6.0:
        return max(natural, 0.85)
    return natural


# ----------------------------------------------------------------------------------- clip tables
def clip_table_from_manifest(path):
    """export/animations.json -> {clip: dict(dur, loop, events=[(t, name), ...])}."""
    with open(path, encoding='utf-8') as f:
        man = json.load(f)
    out = {}
    for name, c in man['clips'].items():
        ev = []
        for k, v in (c.get('events_s') or {}).items():
            for tt in (v if isinstance(v, list) else [v]):
                ev.append((float(tt), k))
        out[name] = dict(dur=float(c['seconds']), loop=bool(c['loop']), events=sorted(ev),
                         blend_in=float(c.get('blend_in_s', 0.3)))
    return out


def clip_table_from_source(path):
    """Read clip names/durations/loop flags (and EVENTS) straight from blender/05_animations.py."""
    src = open(path, encoding='utf-8').read()
    out = {}
    for m in re.finditer(r"@anim\('([a-z_0-9]+)',\s*([0-9.]+)(?:,\s*loop=(True|False))?\)", src):
        out[m.group(1)] = dict(dur=float(m.group(2)), loop=(m.group(3) != 'False'), events=[])
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'EVENTS':
            for name, evs in ast.literal_eval(node.value).items():
                if name in out:
                    out[name]['events'] = sorted((float(tt), k) for k, v in evs.items()
                                                 for tt in (v if isinstance(v, list) else [v]))
    return out


# ----------------------------------------------------------------------------------- the engine
class ConureMind:
    def __init__(self, clips, personality=None, seed=None, time_scale=1.0, bond=0.5, hour=9.0, genome=G):
        self.G = genome
        self.rng = np.random.default_rng(seed)
        self.P = dict(genome.PERSONALITY, **(personality or {}))
        self.h_max = H_MAX
        self.ts = float(time_scale)       # physiology / mood / learning speed-up (demos); emotions stay real-time
        self.F = list(genome.FEATURES)
        self.fi = {f: i for i, f in enumerate(self.F)}
        self.E = list(genome.EMOTIONS)
        self.ei = {e: i for i, e in enumerate(self.E)}
        self.B = list(genome.BEHAVIOURS)
        self.bi = {b: i for i, b in enumerate(self.B)}
        self.clips = clips
        self._build_network()
        self.missing = self._build_behaviours()
        nE, nB = len(self.E), len(self.B)
        # --- state
        self.y = self.be.copy()
        self.e = sig(self.y)
        self.eta = np.zeros(nE)
        self.x = np.zeros(len(self.F))
        self.interest = np.ones(nB)
        self.urge = np.zeros(nB)
        self.bnoise = np.zeros(nB)
        self.hunger, self.S, self.social, self.boredom, self.groom, self.stress = 0.35, 0.2, 0.3, 0.3, 0.3, 0.05
        self.touch, self.neglect, self.pet_dose = 0.35, 0.0, 0.0
        self._last_pet_t = -1e9
        self.last_pet = None              # dict(quality, zone, speed, over) of the most recent stroke
        self._pet_out = None
        self.sleep_drive = 0.0
        self.sleep_debt, self.pressure = 0.0, 0.0     # v5: lost sleep (0..1) and raw sleep pressure
        self._good_pet_t = -1e9                       # v5: time of the last stroke that felt good
        self.scratching = False
        self.tr = {k: 0.0 for k in TRACE_TAU}
        self.held = False
        self.music = 0.0
        self.offer = 0.0
        self.lights_off = False
        self.hour = float(hour)
        self.near = self.fast = self.approach = self.attention = self.looming = 0.0
        self.present = 1.0
        # v4 appraisal layer: raw cursor kinematics + its smoothed judgement units
        self.move = self.jitter = 0.0             # cursor path speed (ref px/s), direction reversals per second
        self.over, self.zone = False, None        # cursor over the bird's silhouette / body zone under it
        self.gentle = self.still = self.head_touch = self.hab_g = 0.0
        self.auto_pet, self._auto_next = 0.0, 0.0  # menu 'Pet': seconds of hand-free head scratching left
        self._irr_shown = False
        self._near_prev = 0.0
        self._loom_prev = 0.0
        self.nov_ema = np.zeros(5)
        self.novelty = 0.0
        self.unanswered = 0.0
        self.absent_s = 0.0
        self.mood_v, self.mood_a = 0.15, 0.3
        self.V = self.A = self.St = 0.0
        # learning
        self.L_time = np.zeros(24)
        self.L_menu = 0.0
        self.exp_pet, self.exp_poke = 0.2, 0.0
        self.bond = float(bond)
        self.hab = 0.0
        self.menu_deadline = None
        self.trial = None                 # cursor-approach trial: dict(deadline, pet, poke)
        self._att_prev = 0.0
        # behaviour / clip
        self.cur = None                   # behaviour name ('feed' during feeding sequences)
        self.clip = None
        self.clip_t = 0.0
        self.clip_dur = 1.0
        self.clip_loop = False
        self.speed = 1.0
        self.recent = []
        self.seq = None
        self.t = 0.0
        self._changed = False
        self._crossfade = 0.3
        self._sounds, self._fx, self._clip_events = [], [], []
        self._pin_phase = 0.0
        self._pin_env, self._pin_hz = 0.0, 2.75
        self._decide(initial=True)

    # ------------------------------------------------------------------ network construction
    def _build_network(self):
        G, E, F = self.G, self.E, self.F
        nE, nF = len(E), len(F)
        self.Wx = np.zeros((nE, nF))
        self.We = np.zeros((nE, nE))
        self.be = np.zeros(nE)
        self.tau = np.zeros(nE)
        self.rise = np.zeros(nE)
        self.sig_n = np.zeros(nE)
        self.anchor = np.zeros((nE, 3))
        for i, name in enumerate(E):
            d = G.EMOTIONS[name]
            self.be[i] = d['bias']
            self.tau[i] = d['tau']
            self.rise[i] = d.get('rise', d['tau'])
            self.sig_n[i] = d['noise'] * self.P.get('volatility', 1.0)
            self.anchor[i] = (d['V'], d['A'], d['S'])
            self.We[i, i] = d.get('self', 0.0)
            for f, w in d['inputs'].items():
                self.Wx[i, self.fi[f]] = w
            for other, w in d.get('inhibit', {}).items():
                self.We[i, self.ei[other]] -= w
        for (dst, src), w in G.EXCITE.items():
            self.We[self.ei[dst], self.ei[src]] += w
        # v4 neuromodulators -> faster decay: tau_eff = tau / (1 + mod x comfort + mod_p x provocation)
        self.mod = np.zeros(nE)
        self.mod_p = np.zeros(nE)
        nm = getattr(G, 'NEUROMOD', {})
        for name, k in nm.get('comfort', {}).items():
            self.mod[self.ei[name]] = k
        for name, k in nm.get('provocation', {}).items():
            self.mod_p[self.ei[name]] = k
        for trait, eff in G.PERSONALITY_EFFECTS.items():
            k = (self.P.get(trait, 0.5) - 0.5) * 2.0
            for name, w in eff.items():
                self.be[self.ei[name]] += w * k

    def _build_behaviours(self):
        G, B = self.G, self.B
        nB, nE, nF = len(B), len(self.E), len(self.F)
        self.bb = np.zeros(nB)
        self.Be = np.zeros((nB, nE))
        self.Bx = np.zeros((nB, nF))
        self.persist = np.full(nB, 1.8)
        self.itau = np.zeros(nB)
        self.urge_rate = np.zeros(nB)
        self.urge_gain = np.zeros(nB)
        self.urge_dis = np.zeros(nB)
        self.priority = np.zeros(nB, int)
        self.gates = []
        self.bclips = []
        missing = []
        group_of = {b: g for g, bs in G.GROUPS.items() for b in bs}
        gbias = getattr(G, 'GROUP_BIAS', {})
        for j, name in enumerate(B):
            d = G.BEHAVIOURS[name]
            self.bb[j] = d.get('bias', 0.0) + gbias.get(group_of.get(name), 0.0)
            for e, w in d.get('emotions', {}).items():
                self.Be[j, self.ei[e]] = w
            for f, w in d.get('features', {}).items():
                self.Bx[j, self.fi[f]] = w
            self.persist[j] = d.get('persist', 1.8)
            self.itau[j] = d.get('interest_tau', 30)
            self.priority[j] = int(d.get('priority', 0))
            u = d.get('urge')
            if u:
                self.urge_rate[j], self.urge_gain[j], self.urge_dis[j] = u['rate_h'] / 3600.0, u['gain'], u['discharge']
            self.gates.append([self._ref(k) + (v,) for k, v in d.get('requires', {}).items()])
            cl = []
            for c in d['clips']:
                name_c, w = c[0], c[1]
                when = [self._ref(k) + tuple(v) for k, v in (c[2] if len(c) > 2 else {}).items()]
                if name_c in self.clips:
                    cl.append((name_c, w, when))
                else:
                    missing.append(name_c)
            self.bclips.append(cl)
            if not cl:
                self.bb[j] = -1e9                    # behaviour has no playable clip
        return sorted(set(missing))

    def _ref(self, key):
        return ('e', self.ei[key]) if key in self.ei else ('x', self.fi[key])

    def _val(self, ref):
        return self.e[ref[1]] if ref[0] == 'e' else self.x[ref[1]]

    # ------------------------------------------------------------------ public API
    def event(self, name, **kw):
        """Discrete user/app events."""
        tr = self.tr
        tr['novelty_ev'] += 0.5
        if name in RESPONSE_EVENTS:
            self.unanswered *= 0.2
        if name in ('pet', 'scratch'):
            self._pet(kw.get('zone'), kw.get('speed'))
        elif name == 'poke':
            tr['poke'] = min(2.0, tr['poke'] + 1.0)
            tr['sudden'] += 1.0 * (1 - self.hab)
            tr['petting'] *= 0.2                            # a poke is not a pet
            tr['comfort'] *= 0.2
            self.auto_pet = 0.0
            self.hab += 0.12 * (1 - self.hab)
            self.stress = min(1.0, self.stress + 0.15 * (1.2 - self.bond))
            self.bond -= 0.02 * self.bond
            self.exp_poke += 0.25 * (1 - self.exp_poke)     # cursor on the bird now predicts being poked
            self.exp_pet -= 0.05 * self.exp_pet
            if self.trial:
                self.trial['poke'] = 1.0
        elif name == 'tap':
            self._tap(kw.get('zone'))
        elif name == 'pet_session':                          # menu 'Pet': a hand-free head scratch
            self.auto_pet = float(self.G.MENU_TOUCH['pet_session_s'])
            self._auto_next = self.t
        elif name == 'poke_once':                            # menu 'Poke'
            self._tap(self.G.MENU_TOUCH['poke_zone'])
        elif name == 'drag_start':
            self.held = True
            tr['sudden'] += 0.4 * (1 - self.hab)          # v3: being carried by its person, not grabbed by a stranger
            self.stress = min(1.0, self.stress + 0.1 * (1 - self.bond))
        elif name == 'drag_end':
            self.held = False
        elif name in ('feed_sunflower', 'feed_millet'):
            kind = 'sunflower' if name == 'feed_sunflower' else 'millet'
            if self.menu_deadline is not None:           # the menu cue predicted food: strengthen it
                self.L_menu += 0.25 * (1 - self.L_menu)
                self.menu_deadline = None
            phi = self._phi()
            self.L_time += 0.3 * (1.0 - float(self.L_time @ phi)) * phi
            # v4: a treat calms - food is the strongest positive reinforcer a companion parrot knows
            tr['comfort'] = min(1.5, tr['comfort'] + self.G.APPRAISAL['comfort_food'])
            tr['pet_bad'] *= 0.6
            tr['poke'] *= 0.7
            tr['irritate'] *= 0.3
            self.stress = max(0.0, self.stress - 0.05)
            self.bond += (0.012 if kind == 'sunflower' else 0.008) * (1 - self.bond)
            self._start_feeding(kind)
        elif name == 'menu_open':
            tr['menu'] = 1.0
            self.menu_deadline = self.t + 20.0
        elif name == 'talk':
            tr['talk'] = min(1.5, tr['talk'] + 1.0)
            self.social = max(0.0, self.social - 0.1)
            self.bond += 0.004 * (1 - self.bond)
        elif name == 'play':
            tr['play_inv'] = min(1.5, tr['play_inv'] + 1.0)
            self.boredom = max(0.0, self.boredom - 0.15)
            self.bond += 0.005 * (1 - self.bond)
        elif name == 'music_on':
            self.music = 1.0
        elif name == 'music_off':
            self.music = 0.0
        elif name == 'lights_off':
            self.lights_off = True
        elif name == 'lights_on':
            self.lights_off = False
            tr['sudden'] += 0.3
        elif name == 'wake':
            tr['sudden'] += 0.5
        elif name == 'fly':                                  # menu 'Fly': take off, hover, land (v5)
            if self.cur != 'sleep' and self.seq is None:
                self._start_flight()
        self.bond = clamp(self.bond)

    def update(self, dt, percepts=None):
        """Advance by dt seconds; returns the output dict for this frame."""
        p = percepts or {}
        self._read_percepts(p, dt)
        n = max(1, int(math.ceil(dt / self.h_max - 1e-9)))
        h = dt / n
        for _ in range(n):
            self._step(h)
        return self._output(dt)

    # ------------------------------------------------------------------ touch (v2)
    def pet_quality(self, zone=None, speed=None, gap=1.0):
        """How a stroke feels to the bird, 0 (nothing) .. +1 (lovely). v4: hovering is never unpleasant - too fast
        fades to 0 (frantic scrubbing is judged by the appraisal layer), too long = satiation. Returns (q, over, upset)."""
        P = self.G.PETTING
        zv = max(0.0, P['zones'].get(zone or 'head', 0.1))
        sp = 150.0 if speed is None else float(speed)
        lo, hi = P['speed_good']
        rough = clamp((sp - hi) / (P['speed_rough'] - hi))
        gentle = 0.6 + 0.4 * clamp(sp / lo)                 # very slow strokes are barely felt
        q = zv * gentle * (1 - rough)
        tol = P['tolerance_s'] * (0.4 + self.touch + 0.5 * self.bond)
        over = max(0.0, self.pet_dose + gap - tol) / tol
        q *= clamp(1.0 - over)                               # satiation: enough for now
        if self.cur == 'sleep':
            q *= 0.5
        e = self.e
        upset = clamp(max(e[self.ei['angry']], e[self.ei['afraid']] - 0.2, e[self.ei['frustrated']] - 0.2))
        return clamp(q), over, upset

    def _pet(self, zone=None, speed=None):
        tr, P, A = self.tr, self.G.PETTING, self.G.APPRAISAL
        gap = clamp(self.t - self._last_pet_t, 0.05, 2.0)     # seconds of stroking this event stands for
        self._last_pet_t = self.t
        q, over, upset = self.pet_quality(zone, speed, gap)
        self.pet_dose += gap
        k = clamp(gap / 2.0, 0.15, 1.0)
        if self.cur == 'sleep':
            tr['sudden'] += 0.3 * (1 - self.hab)
        if q > 0:
            share = P['upset_share'] * upset                 # an upset bird is calmed first, enjoys it later
            pleasure = q * (1 - share)
            tr['petting'] = min(1.5, tr['petting'] + 0.6 * pleasure * clamp(gap, 0.25, 1.0))
            tr['comfort'] = min(1.5, tr['comfort'] + A['comfort_pet'] * q * clamp(gap, 0.25, 1.0))
            so = P['soothe']
            for key in ('pet_bad', 'poke', 'irritate'):
                tr[key] *= 1 - so[key] * q
            self.stress = max(0.0, self.stress - so['stress'] * q)
            self.social = max(0.0, self.social - 0.12 * q * k)
            self.touch = max(0.0, self.touch - 0.10 * q * k)
            self.groom = max(0.0, self.groom - 0.02 * k)
            self.neglect = max(0.0, self.neglect - 0.12 * q * k)
            self.bond += 0.006 * q * k * (1 - self.bond)
            self.exp_pet += 0.08 * q * k * (1 - self.exp_pet)      # cursor on the bird predicts a nice scratch
            self.exp_poke -= 0.03 * q * k * self.exp_poke
            if q > 0.15:
                self._good_pet_t = self.t
            if self.trial:
                self.trial['pet'] = 1.0
        self.bond = clamp(self.bond)
        self.last_pet = dict(quality=round(q, 3), zone=zone or 'head', speed=speed, over=round(over, 3))
        self._pet_out = self.last_pet

    def _tap(self, zone=None):
        """A left click on the bird (v4): always a poke, graded by zone (genome TAP); repeated clicks escalate."""
        T = self.G.TAP
        zone = zone or 'chest'
        spec = T['zones'].get(zone, T['default'])
        tr = self.tr
        a = spec['annoy'] * (1.3 - 0.6 * self.bond)            # a trusting bird forgives more
        if self.cur == 'sleep':
            a += 0.3
        tr['pet_bad'] = min(1.5, tr['pet_bad'] + a)
        tr['poke'] = min(2.0, tr['poke'] + T['poke_gain'] * a)   # clicks add up: a bit angry -> really angry
        tr['petting'] *= 0.1                                   # a poke ends the cuddle
        tr['comfort'] *= 0.05
        self.auto_pet = 0.0                                    # ... including a menu 'Pet' session
        self.head_touch = 0.0                                  # the hand is poking now, not resting on the head
        tr['sudden'] += spec.get('startle', 0.3) * (1 - self.hab)
        self.hab += 0.05 * (1 - self.hab)
        self.stress = min(1.0, self.stress + 0.05 * a * (1.2 - self.bond))
        self.exp_poke += 0.06 * a * (1 - self.exp_poke)
        self.bond = clamp(self.bond - 0.004 * a * self.bond)
        if self.trial:
            self.trial['poke'] = max(self.trial['poke'], 0.5 * a)
        if spec.get('sound') and self.rng.random() < min(1.0, 0.5 + a):
            self._sounds.append(spec['sound'])
        self.last_pet = dict(quality=round(-a, 3), zone=zone, speed=None, over=0.0, tap=True)
        self._pet_out = self.last_pet

    def hand_signals(self):
        """(good, bad, sad): what the approaching cursor (the hand) means right now."""
        prox = clamp(1.6 * self.near - 0.15 + 0.5 * self.approach) * self.present     # ~0 beyond 400 px
        H = clamp(self.exp_pet - self.exp_poke + 0.3 * (self.bond - 0.5), -1.0, 1.0)
        mood = clamp(0.7 + 1.5 * self.mood_v, 0.3, 1.2)
        good = prox * clamp(2.5 * H) * (1 - self.neglect) * mood
        bad = prox * clamp(-2.5 * H)
        sad = prox * clamp(2.4 * self.neglect - 0.1) * (1 - clamp(-2.5 * H))
        return clamp(good), clamp(bad), clamp(sad)

    # ------------------------------------------------------------------ senses
    def _read_percepts(self, p, dt):
        if 'hour' in p:
            self.hour = float(p['hour'])
        d = p.get('cursor_dist')
        near = math.exp(-d / 250.0) if d is not None else 0.0
        self.fast = 1.0 - math.exp(-p.get('cursor_speed', 0.0) / 1500.0)
        self.present = math.exp(-p.get('idle_s', 0.0) / 240.0)
        if 'music' in p:
            self.music = float(p['music'])
        if 'held' in p:
            self.held = bool(p['held'])
        self.move = float(p.get('cursor_move', 0.0) or 0.0)          # v4: raw path speed, ref px/s
        self.jitter = float(p.get('cursor_jitter', 0.0) or 0.0)      # direction reversals per second
        self.over = bool(p.get('cursor_over', False))
        self.zone = p.get('cursor_zone')
        if dt > 0:
            a = max(0.0, (near - self._near_prev) / dt) * 2.0
            self.approach += (clamp(a) - self.approach) * (1 - math.exp(-dt / 1.0))
        self._near_prev = near
        self.near = near

    def _phi(self):
        c = np.arange(24) + 0.5
        dh = (self.hour - c + 12.0) % 24.0 - 12.0
        return np.exp(-0.5 * (dh / 0.75) ** 2)

    # ------------------------------------------------------------------ one integration step
    def _step(self, h):
        G, D = self.G, self.G.DRIVES
        hp = h * self.ts
        self.t += h
        tr = self.tr
        if self.held:
            tr['held'] = 1.0
        # --- smoothed senses
        att = self.near * (1 - self.fast) * self.present
        self.attention += (att - self.attention) * (1 - math.exp(-h / 1.5))
        loom = self.near * self.fast
        if loom > 0.45 and self._loom_prev <= 0.45:      # something rushes at the bird
            tr['sudden'] += 0.6 * (1 - self.hab)
            self.hab += 0.15 * (1 - self.hab)
        self._loom_prev = loom
        self.looming += (loom - self.looming) * (1 - math.exp(-h / 0.3))
        self.hab *= math.exp(-hp / (600.0 * (1.5 - self.P['neuroticism'])))
        # --- reunion / absence
        if self.present < 0.2:
            self.absent_s += hp
        elif self.present > 0.6:
            if self.absent_s > 600:
                tr['reunion'] += min(1.5, 0.5 + 0.6 * math.log10(self.absent_s / 600.0)) * (0.5 + self.bond)
            self.absent_s = 0.0
        # --- cursor-approach trials (does approach predict petting or poking?)
        if self.attention > 0.5 and self._att_prev <= 0.5 and self.trial is None:
            self.trial = dict(deadline=self.t + 8.0, pet=0.0, poke=0.0)
        self._att_prev = self.attention
        if self.trial and self.t > self.trial['deadline']:     # approach that brought nothing: slow extinction
            if not self.trial['pet']:
                self.exp_pet -= 0.03 * self.exp_pet
                if self.touch > 0.4:                               # the hand came, but no scratch: disappointment
                    self.neglect = clamp(self.neglect + 0.05 * self.touch)
            if not self.trial['poke']:
                self.exp_poke -= 0.05 * self.exp_poke
            self.trial = None
        if self.menu_deadline is not None and self.t > self.menu_deadline:
            self.L_menu += 0.125 * (0.0 - self.L_menu)
            self.menu_deadline = None
        # --- body
        asleep = self.cur == 'sleep'
        if self.lights_off and 7.0 <= self.hour % 24 < 7.1:
            self.lights_off = False
        light = light_level(self.hour, self.lights_off, self.present)
        night = 1.0 - light
        met = 0.3 if asleep else 1.0
        self.hunger += (1 - self.hunger) * (1 - math.exp(-hp * met / (D['hunger_rise_h'] * 3600)))
        if self.hunger > D['hunger_bowl']:
            self.hunger -= (self.hunger - D['hunger_bowl']) * (1 - math.exp(-hp / 1800.0))
        if asleep:
            self.S *= math.exp(-hp / (D['sleep_fall_h'] * 3600))
        else:
            self.S += (1 - self.S) * (1 - math.exp(-hp / (D['sleep_rise_h'] * 3600)))
        siesta = math.exp(-((self.hour - 13.5) / 1.2) ** 2)
        SD = G.SLEEP_DEBT
        dark = max(night, SD['lamp_night'] * bio_night(self.hour, SD['bio_night']))   # v5: own clock under the lamp
        self.pressure = clamp(1.25 * self.S + 0.85 * dark - 0.5)
        if asleep or self.cur == 'doze':                   # v5: only sleep repays lost sleep
            rh = SD['recover_h'] if asleep else SD['recover_doze_h']
            if night < 0.5:
                rh /= SD['lit_factor']
            self.sleep_debt *= math.exp(-hp / (rh * 3600))
        if not asleep:
            over = clamp((self.pressure - SD['threshold']) / SD['span'])
            self.sleep_debt += (1 - self.sleep_debt) * over * (1 - math.exp(-hp / (SD['rise_h'] * 3600)))
        self.sleep_drive = clamp(1.25 * self.S + 0.85 * dark + 0.2 * siesta + SD['drive_gain'] * self.sleep_debt
                                 - 0.5 - 0.6 * self.stress)
        if not asleep and night < 0.5:                     # roosting in the dark: no flock-calling urge
            tau_s = D['social_rise_min'] * 60 * (1.5 - self.P['extraversion']) * (1 + 2 * self.present)
            self.social += (1 - self.social) * (1 - math.exp(-hp / tau_s))
            self.boredom += (1 - self.boredom) * (1 - math.exp(-hp / (D['boredom_rise_min'] * 60)))
            self.groom += (1 - self.groom) * (1 - math.exp(-hp / (D['groom_rise_min'] * 60)))
        self.social -= self.social * (1 - math.exp(-hp * self.attention / D['social_fill_s']))
        if not asleep and night < 0.5:                     # need for head scratches (not filled by looking)
            tau_t = D['touch_rise_min'] * 60 / (0.5 + self.bond)
            self.touch += (1 - self.touch) * (1 - math.exp(-hp / tau_t))
        unmet = clamp(self.touch - 0.5) * self.present
        if not asleep and unmet > 0 and tr['petting'] < 0.1:
            self.neglect += (1 - self.neglect) * unmet * hp / (D['neglect_rise_min'] * 60)
        cheer = 0.3 * self.attention + 0.5 * tr['talk'] + 0.5 * tr['play_inv']
        self.neglect *= math.exp(-hp / (D['neglect_decay_min'] * 60)) * math.exp(-hp * cheer / 900.0)
        self.pet_dose *= math.exp(-hp / self.G.PETTING['dose_tau_s'])
        relief = 2 * self.novelty + tr['play_inv'] + 0.5 * tr['talk']
        self.boredom -= self.boredom * (1 - math.exp(-hp * relief / 60.0))
        self.stress *= math.exp(-hp / (D['stress_decay_min'] * 60 * (1 + self.P['neuroticism'])))
        if self.present < 0.2:
            self.bond -= (self.bond - 0.3) * hp / (14 * 86400.0)
        # --- novelty (change detector)
        ch = np.array([self.near, self.present, self.music, night, self.fast])
        self.nov_ema += (ch - self.nov_ema) * (1 - math.exp(-h / 60.0))
        self.novelty = clamp(1.5 * float(np.abs(ch - self.nov_ema).sum()) + tr['novelty_ev'])
        # --- learning: expected food now (time-of-day habit + menu cue), extinction when it doesn't come
        phi = self._phi()
        p_time = clamp(float(self.L_time @ phi))
        if self.present > 0.5 and self.seq is None and p_time > 0.01:
            self.L_time -= 3.7e-5 * hp * p_time * phi
            np.clip(self.L_time, 0.0, 1.0, out=self.L_time)
        # --- unanswered requests (frustration source)
        if self.cur and self.cur in self.bi and self.G.BEHAVIOURS[self.cur].get('request'):
            self.unanswered += (1 - self.unanswered) * h / 40.0
        else:
            self.unanswered *= math.exp(-h / 300.0)
        # --- v4 appraisal layer: what is the hand DOING? (leaky units over the raw cursor kinematics)
        A = G.APPRAISAL
        mv, near = self.move, self.near
        g0, g1, g2, g3 = A['gentle_speed']
        band = smoothstep(mv, g0, g1) * (1.0 - smoothstep(mv, g2, g3))
        close = smoothstep(near, *A['frantic_close'])
        frantic = close * smoothstep(mv, *A['frantic_speed']) * smoothstep(self.jitter, *A['frantic_jitter'])
        on_head = 1.0 if (self.over and self.zone in A['head_zones'] and mv < A['head_still_max']) else 0.0
        if self.auto_pet > 0:                                   # menu 'Pet': the (invisible) hand is on the head
            on_head = 1.0
            self.auto_pet -= h
            if self.t >= self._auto_next:
                self._auto_next = self.t + 0.25
                self._pet('head', self.G.MENU_TOUCH['pet_speed'])
        near_g = near ** (250.0 / A['gentle_radius_px'])        # exp(-d / gentle_radius)
        gentle_raw = near_g * band * (1.0 - frantic) * (1.0 - on_head) * self.present
        still_raw = clamp(1.8 * near - 0.5) * (1.0 - smoothstep(mv, *A['still_speed'])) * (1.0 - on_head) * self.present
        self.gentle += (gentle_raw - self.gentle) * (1 - math.exp(-h / 1.2))
        self.still += (still_raw - self.still) * (1 - math.exp(-h / 0.8))
        self.head_touch += (on_head - self.head_touch) * (1 - math.exp(-h / (0.5 if on_head > self.head_touch else 1.2)))
        hb, hr = A['gentle_habituation_s']                      # constant cursor play gets less exciting
        if gentle_raw > self.hab_g:
            self.hab_g += (gentle_raw - self.hab_g) * (1 - math.exp(-hp / hb))
        else:
            self.hab_g *= math.exp(-hp / hr)
        tr['irritate'] = min(1.2, tr['irritate'] + A['irritation_rate'] * frantic * h)
        tr['comfort'] *= math.exp(-A.get('frantic_drain', 2.0) * frantic * h)   # being scrubbed is not comforting
        tr['comfort'] = min(1.5, tr['comfort'] + A['comfort_head'] * self.head_touch * h)
        # v5: sleep debt amplifies provocation and blunts soothing (Yoo et al. 2007) - a treat does not fix it
        debt = self.sleep_debt
        amp, blunt = 1.0 + SD['amplify'] * debt, 1.0 - SD['blunt'] * debt
        comfort = clamp(tr['comfort']) * blunt
        # v5: is the bird still being scratched? (a good stroke in the last scratch_gap_s, or the hand on the head)
        self.scratching = (self.t - self._good_pet_t < A['scratch_gap_s']) or self.head_touch > 0.35 \
            or self.auto_pet > 0
        # --- feature vector
        bias = self.mood_v - (self.P['neuroticism'] - 0.5) * 0.3
        amb = clamp(self.fast * (0.3 + self.near))
        x, fi = self.x, self.fi
        x[fi['hunger']] = self.hunger
        x[fi['sleep_drive']] = self.sleep_drive
        x[fi['social_need']] = self.social
        x[fi['boredom']] = self.boredom
        x[fi['groom_need']] = self.groom
        x[fi['stress']] = self.stress
        x[fi['present']] = self.present
        x[fi['alone']] = 1 - self.present
        x[fi['cursor_near']] = self.near
        x[fi['cursor_fast']] = self.fast
        x[fi['approach']] = self.approach
        x[fi['attention']] = self.attention
        x[fi['looming']] = self.looming
        x[fi['petting']] = clamp(tr['petting'])
        x[fi['poke']] = clamp(tr['poke'] * amp, 0, 1.5)    # repeated pokes escalate
        x[fi['held']] = clamp(tr['held'])
        x[fi['reward_sun']] = clamp(tr['reward_sun']) * blunt
        x[fi['reward_mil']] = clamp(tr['reward_mil']) * blunt
        x[fi['offer']] = self.offer * blunt
        x[fi['music']] = self.music
        x[fi['novelty']] = self.novelty
        x[fi['talk']] = clamp(tr['talk'])
        x[fi['play_inv']] = clamp(tr['play_inv'])
        x[fi['reunion']] = clamp(tr['reunion'])
        x[fi['sudden']] = clamp(tr['sudden'], 0, 1.5)
        x[fi['night']] = night
        x[fi['just_woke']] = clamp(tr['just_woke'])
        x[fi['exp_food']] = clamp(p_time * self.present + self.L_menu * tr['menu'])
        x[fi['exp_pet']] = self.exp_pet * self.attention
        x[fi['exp_poke']] = self.exp_poke * max(self.attention, self.approach)
        x[fi['bond']] = self.bond
        x[fi['mood_pos']] = clamp(self.mood_v * 2.5)
        x[fi['mood_neg']] = clamp(-self.mood_v * 2.5)
        x[fi['amb_pos']] = amb * clamp(bias * 4)
        x[fi['amb_neg']] = amb * clamp(-bias * 4)
        x[fi['unanswered']] = self.unanswered
        x[fi['social_seek']] = self.social * self.present
        # v4: only provocation (clicks, being carried) makes a sleepy bird grumpy; a hand, talk or petting just wakes it
        x[fi['disturb_sleep']] = self.sleep_drive * clamp(tr['poke'] + 0.5 * tr['pet_bad'] + 0.3 * tr['held'])
        hg, hb, hs = self.hand_signals()
        x[fi['touch_need']] = self.touch
        x[fi['pet_bad']] = clamp(tr['pet_bad'] * amp)
        x[fi['hand_good']] = hg
        x[fi['hand_bad']] = hb
        x[fi['hand_sad']] = hs
        x[fi['neglect']] = self.neglect
        x[fi['cursor_gentle']] = self.gentle * (1.0 - A['gentle_habituation_max'] * self.hab_g)
        x[fi['cursor_still']] = self.still
        x[fi['head_touch']] = self.head_touch
        x[fi['irritation']] = clamp(tr['irritate'] * amp)
        x[fi['annoyed']] = max(x[fi['pet_bad']], x[fi['irritation']])
        x[fi['comfort']] = comfort
        x[fi['sleep_debt']] = debt
        # --- emotion CTRNN (exponential Euler, stable for any h)
        self.eta += -self.eta * h / 90.0 + self.sig_n * math.sqrt(2 * h / 90.0) * self.rng.standard_normal(len(self.E))
        net = self.Wx @ x + self.We @ self.e + self.be + self.eta
        dy = net - self.y
        provoke = clamp(tr['poke'] + 0.5 * tr['pet_bad'] + tr['sudden'])
        decay = self.tau / (1.0 + self.mod * comfort + self.mod_p * provoke)   # v4 neuromodulation
        self.y += dy * (1 - np.exp(-h / np.where(dy > 0, self.rise, decay)))        # fast attack, slow release
        self.e = sig(self.y)
        # --- core affect + mood
        w = self.e
        sw = 0.6 + w.sum()
        self.V = float(w @ self.anchor[:, 0]) / sw
        self.A = (0.15 + float(w @ self.anchor[:, 1])) / sw
        self.St = float(w @ self.anchor[:, 2]) / sw
        k = 1 - math.exp(-hp / (D['mood_tau_min'] * 60))
        self.mood_v += (self.V - self.mood_v) * k
        self.mood_a += (self.A - self.mood_a) * k
        # --- behaviour bookkeeping
        j = self.bi.get(self.cur, -1)
        old = self.interest[j] if j >= 0 else 0.0
        self.interest += (1 - self.interest) * (1 - np.exp(-h / (2 * self.itau)))     # recovers while not doing it
        if j >= 0:
            self.interest[j] = old * math.exp(-h / self.itau[j])                       # wanes while doing it
        self.urge += self.urge_rate * hp * (1 - self.sleep_drive)
        if j >= 0:                                        # what the current behaviour does to the body (per minute)
            for k, v in self.G.BEHAVIOURS[self.cur].get('effects', {}).items():
                d = v * hp / 60.0
                if k == 'sleep':
                    self.S = clamp(self.S + d)
                elif k == 'groom_need':
                    self.groom = clamp(self.groom + d)
                elif k == 'boredom':
                    self.boredom = clamp(self.boredom + d)
                elif k == 'social_need':
                    self.social = clamp(self.social + d)
                elif k == 'reunion':
                    tr['reunion'] = max(0.0, tr['reunion'] + d)
        self.bnoise += -self.bnoise * h / 60.0 + 0.5 * math.sqrt(2 * h / 60.0) * self.rng.standard_normal(len(self.B))
        # --- clip playback + decisions
        if self.clip is not None:
            t0 = self.clip_t
            self.clip_t += h * self.speed
            for tt, nm in self.clips[self.clip]['events']:
                if t0 <= tt < self.clip_t:
                    self._clip_events.append((self.clip, nm))
            if self.seq is not None and self.seq.get('kind') == 'fly':     # v5: hover = loop the airborne part
                a, b = self.seq['loop']
                if self.seq['left'] > 0 and self.clip_t >= b:
                    self.clip_t -= (b - a)
                    self.seq['left'] -= 1
            if self.clip_t >= self.clip_dur:
                self._clip_done()
        if self.cur == 'enjoy_petting' and not self.scratching and self.seq is None:
            tr['petting'] *= 0.4                          # v5: the hand left the head -> stop the scratch pose now
            self._decide()
        self._interrupt_check()
        for k, tau in TRACE_TAU.items():                  # event traces decay after the network has seen them
            tr[k] *= math.exp(-h / tau)
        if comfort > 0:                                   # v4: being comforted, the bird lets go of the provocation
            f = math.exp(-h * comfort / 8.0)
            tr['pet_bad'] *= f
            tr['poke'] *= f
        # --- Poisson physiology
        if self.cur not in ('sleep', 'feed', 'fly') and 'sneeze' in self.clips and \
                self.rng.random() < self.G.POISSON['sneeze'] * h:
            self._play('sneeze', self.cur, crossfade=0.2)

    # ------------------------------------------------------------------ behaviour selection
    def _motivations(self):
        m = self.bb + self.Be @ self.e + self.Bx @ self.x + self.urge_gain * self.urge
        m = m - 2.5 * (1 - self.interest) + self.bnoise
        j = self.bi.get(self.cur, -1)
        if j >= 0:
            m[j] += self.persist[j]
        stay = getattr(self.G, 'SELECTION', {}).get('stay_gate', 1.0)
        ok = np.ones(len(self.B), bool)
        for b, gate in enumerate(self.gates):
            k = stay if b == j else 1.0                      # v4 hysteresis: easier to stay than to start
            for kind, idx, lo in gate:
                if (self.e[idx] if kind == 'e' else self.x[idx]) < lo * k:
                    ok[b] = False
                    break
        jp = self.bi.get('enjoy_petting', -1)
        if jp >= 0 and not self.scratching:              # v5: no scratch without a hand on the head
            ok[jp] = False
        m[~ok] = -np.inf
        return m

    def _decide(self, initial=False):
        m = self._motivations()
        j = self.bi.get(self.cur, -1)
        if not initial and j >= 0 and self.priority[j] > 0 and np.isfinite(m[j]):
            # v4: a priority behaviour whose trigger is still there (being scratched, startled, greeting) is not
            # swapped out by chance at the end of its clip - that read as a glitch (pose out and straight back in)
            others = np.delete(m, j)
            if m[j] >= np.max(others) - getattr(self.G, 'SELECTION', {}).get('keep_margin', 0.0):
                return self._start_behaviour(self.cur, crossfade=0.3)
        T = 0.4 * (1 + 0.6 * self.A) * self.P.get('volatility', 1.0)
        z = (m - np.max(m)) / T
        p = np.exp(z)
        p /= p.sum()
        b = int(self.rng.choice(len(self.B), p=p))
        self._start_behaviour(self.B[b], crossfade=0.0 if initial else 0.3)

    def _interrupt_check(self):
        """Priority behaviours (startle 3 > fear/threat 2 > greet/petting 1) may cut the playing clip short."""
        if self.seq is not None:
            return
        m = self._motivations()
        j = self.bi.get(self.cur, -1)
        mc = m[j] if j >= 0 else -np.inf
        rc = self.priority[j] if j >= 0 else 0
        m_pri = np.where(self.priority > 0, m, -np.inf)
        b = int(np.argmax(m_pri + 10 * self.priority * np.isfinite(m_pri)))   # highest rank first
        if b == j or not np.isfinite(m_pri[b]):
            return
        if (self.priority[b] > rc and m_pri[b] > mc - self.persist[j if j >= 0 else b]) or m_pri[b] > mc + 1.0:
            self._start_behaviour(self.B[b], crossfade=0.15)

    def _start_behaviour(self, name, crossfade=0.3):
        j = self.bi[name]
        cands = []
        for clip, w, when in self.bclips[j]:
            if all(lo <= self._val((k, i)) <= hi for k, i, lo, hi in when):
                if clip in self.recent[-3:] and not (name == self.cur and clip == self.clip):
                    w *= 0.3
                if name == self.cur and clip == self.clip:
                    w *= 2.5                                   # loops tend to continue
                cands.append((clip, w))
        if not cands:
            cands = [(c, w) for c, w, _ in self.bclips[j]]
        ws = np.array([w for _, w in cands], float)
        clip = cands[int(self.rng.choice(len(cands), p=ws / ws.sum()))][0]
        if self.cur == 'sleep' and name != 'sleep':
            self._woken()
        self._play(clip, name, crossfade)

    def _play(self, clip, behaviour, crossfade=0.3):
        same = (clip == self.clip and behaviour == self.cur and self.clip_loop)
        self.cur = behaviour
        c = self.clips[clip]
        if same:
            self.clip_t = max(0.0, self.clip_t - self.clip_dur)
        else:
            self.clip, self.clip_dur, self.clip_loop = clip, c['dur'], c['loop']
            self.clip_t = 0.0
            self._changed = True
            self._crossfade = max(crossfade, c.get('blend_in', 0.0)) if crossfade > 0 else 0.0
            self.recent = (self.recent + [clip])[-6:]
        calm = behaviour in ('rest', 'doze', 'sleep', 'watch_user', 'look_around')
        sp = 0.92 + 0.22 * self.A + self.rng.normal(0, 0.03)
        if calm:
            sp *= 0.95
        self.speed = 1.0 if behaviour in ('feed', 'fly') else clamp(sp, 0.8, 1.2)

    def _clip_done(self):
        j = self.bi.get(self.cur, -1)
        if j >= 0:
            self.urge[j] *= (1 - self.urge_dis[j])
        if self.seq is not None:
            self._seq_next()
        else:
            self._decide()

    # ------------------------------------------------------------------ feeding sequences
    def _start_feeding(self, kind):
        self.seq = dict(kind=kind, stage='see', loops=0)
        self.offer = self.G.FEEDING[kind].get('value', 1.0)
        if self.cur == 'sleep':
            self.tr['sudden'] += 0.3
            self._woken()
        self.unanswered = 0.0
        self._play(self.G.FEEDING[kind]['see'], 'feed', crossfade=0.2)

    def _woken(self):
        """Leaving sleep. Woken while still sleepy (by the user, a treat, a noise) costs sleep (v5)."""
        self.tr['just_woke'] = 1.0
        if self.pressure > 0.35:
            self.sleep_debt = clamp(self.sleep_debt + self.G.SLEEP_DEBT['wake_penalty'] * self.pressure)

    # ------------------------------------------------------------------ flight (v5)
    def _start_flight(self):
        F = self.G.FLY
        if F['clip'] not in self.clips:
            return
        self.seq = dict(kind='fly', loop=tuple(F['loop']), left=int(F['repeats']))
        self.tr['play_inv'] = min(1.5, self.tr['play_inv'] + 0.5)   # a flight is exercise and fun
        self.boredom = max(0.0, self.boredom - 0.2)
        self._play(F['clip'], 'fly', crossfade=0.25)
        self.speed = 1.0

    def _logit(self, spec):
        a, wa, b, wb, c = spec
        va = self.e[self.ei[a]] if a in self.ei else self.x[self.fi[a]]
        vb = self.e[self.ei[b]] if b in self.ei else self.x[self.fi[b]]
        return 1.0 / (1.0 + math.exp(-(wa * va + wb * vb + c)))

    def _seq_next(self):
        if self.seq['kind'] == 'fly':                      # landed
            self.seq = None
            return self._decide()
        s, F = self.seq, self.G.FEEDING[self.seq['kind']]
        food = self.G.DRIVES['food']
        if s['stage'] in ('see', 'beg'):
            if F['beg'] and s['loops'] < F['max_loops'] and self.rng.random() < self._logit(F['beg_logit']):
                s['stage'], s['loops'] = 'beg', s['loops'] + 1
                return self._play(F['beg'], 'feed', 0.15)
            s['stage'] = 'eat'
            return self._play(F['eat'], 'feed', 0.15)
        if s['stage'] == 'eat':
            self.hunger = max(0.0, self.hunger - food[s['kind']])
            self.tr['reward_sun' if s['kind'] == 'sunflower' else 'reward_mil'] += 1.0
            self.offer *= 0.3
            s['loops'] = 0
        elif s['stage'] == 'more':
            self.hunger = max(0.0, self.hunger - food['millet_nibble'])
            self.tr['reward_mil'] += 0.2
        if F['more'] and s['loops'] < F['max_loops'] and self.rng.random() < self._logit(F['more_logit']):
            s['stage'], s['loops'] = 'more', s['loops'] + 1
            return self._play(F['more'], 'feed', 0.15)
        self.seq = None
        self.offer = 0.0
        self._decide()

    # ------------------------------------------------------------------ outputs
    def _output(self, dt):
        e = {n: float(v) for n, v in zip(self.E, self.e)}
        rng = self.rng
        ex = max(e['excited'], e['angry'] * 0.9, e['proud'] * 0.8, e['hungry'] * self.offer)
        # v4 eye pinning: an excitement / aggression display. Smooth envelope (no on/off at a threshold = no flicker),
        # a steady 2-3.5 Hz rhythm, and none while the bird is calm or affectionate (resting, preening, being scratched).
        calm = self.cur in CALM_BEHAVIOURS
        env = 0.0 if calm else smoothstep(ex, 0.4, 0.7)
        self._pin_env += (env - self._pin_env) * (1 - math.exp(-dt / 0.3))
        self._pin_hz += (2.75 - self._pin_hz) * dt / 5.0 + 0.6 * math.sqrt(dt) * rng.standard_normal() * 0.3
        self._pin_hz = clamp(self._pin_hz, 2.0, 3.5)
        self._pin_phase += dt * self._pin_hz * math.pi * 2
        pin = self._pin_env * ex * (0.55 + 0.45 * math.sin(self._pin_phase))
        crest = 25 * max(e['excited'], 0.6 * e['curious'], e['startled'], 0.8 * e['angry'], 0.7 * e['proud']) \
            - 15 * e['afraid'] - 12 * e['sad'] - 8 * e['sleepy']
        fluff = 1 + 0.07 * e['content'] + 0.06 * e['sleepy'] + 0.07 * e['angry'] + 0.05 * e['affectionate'] \
            - 0.07 * e['afraid']
        lam = max(0.02, self.G.POISSON['blink_base'] + self.G.POISSON['blink_sleepy'] * e['sleepy']
                  + self.G.POISSON['blink_afraid'] * e['afraid'] - 0.08 * e['excited'])
        blink = None
        if self.cur != 'sleep' and rng.random() < lam * dt:
            blink = 'slow' if (e['affectionate'] > 0.5 or e['content'] > 0.6) else 'fast'
        look = clamp(0.9 * e['curious'] + e['affectionate'] + e['excited'] + e['hungry'] * self.present
                     + e['afraid'] * self.near + 0.8 * e['proud'] + e['angry'] * self.near
                     - e['sad'] - 0.5 * e['bored'])
        sacc = rng.random() < (self.G.POISSON['saccade_base'] + 0.8 * e['afraid'] + 0.4 * e['curious']) * dt
        hg, hb, hs = self.hand_signals()
        sounds = list(self._sounds)
        for kind, rate in (('chirp', 0.05 * e['happy'] + 0.12 * e['excited'] + 0.03 * e['affectionate']),
                           ('whistle', 0.04 * e['proud']), ('grumble', 0.05 * e['angry'] + 0.25 * e['angry'] * hb
                                       + 0.05 * e['frustrated'] * self.sleep_debt),
                           ('alarm', 0.06 * e['afraid']), ('grind', 0.05 * e['content'] * e['sleepy']),
                           ('excited', 0.25 * e['excited'] * hg), ('click', 0.03 * e['curious'] + 0.1 * e['angry'] * hb)):
            if self.cur != 'sleep' and rng.random() < rate * dt:
                sounds.append(kind)
        fx = list(self._fx)
        if e['affectionate'] > 0.5 and self.tr['petting'] > 0.2 and rng.random() < 1.2 * dt:
            fx.append('heart')
        if self.cur == 'sleep' and rng.random() < 0.5 * dt:
            fx.append('zzz')
        if self._changed and self.cur == 'startle':
            fx.append('!')
        if self._changed and self.cur == 'investigate':
            fx.append('?')
        if e['angry'] > 0.6 and rng.random() < 0.8 * dt:
            fx.append('anger')
        if self.music > 0.5 and self.cur == 'play' and rng.random() < 1.5 * dt:
            fx.append('note')
        if self._pet_out is not None:
            fx.append('heart' if self._pet_out['quality'] > 0.4 else 'anger' if self._pet_out['quality'] < -0.4 else '')
            fx = [f for f in fx if f]
        if e['sad'] > 0.4 and hs > 0.25 and rng.random() < 0.6 * dt:
            fx.append('sad')
        irr = self.tr['irritate']                          # v4: frantic cursor -> one light 'annoyed' mark + click
        if irr > 0.5 and not self._irr_shown:
            self._irr_shown = True
            fx.append('annoyed')
            sounds.append('click')
        elif irr < 0.2:
            self._irr_shown = False
        if self.head_touch > 0.7 and e['content'] > 0.5 and rng.random() < 0.35 * dt:
            fx.append('heart')
        dom = max(e, key=e.get)
        out = dict(clip=self.clip, clip_time=self.clip_t, speed=self.speed, loop=self.clip_loop,
                   changed=self._changed, crossfade=self._crossfade, behaviour=self.cur,
                   emotion=dom if e[dom] > 0.25 else 'neutral', emotions=e,
                   affect=dict(valence=self.V, arousal=self.A, stance=self.St),
                   mood=dict(valence=self.mood_v, arousal=self.mood_a),
                   drives=dict(hunger=self.hunger, sleep=self.sleep_drive, social=self.social, boredom=self.boredom,
                               groom=self.groom, stress=self.stress, bond=self.bond, sleep_debt=self.sleep_debt,
                               sleep_pressure=self.pressure),
                   hold=(dict(start=self.seq['loop'][0], end=self.seq['loop'][1], repeats=self.G.FLY['repeats'],
                              lift=self.G.FLY.get('lift_scale', 1.0))
                         if self.seq is not None and self.seq.get('kind') == 'fly' else None),
                   learned=dict(food_now=float(self.x[self.fi['exp_food']]), menu=self.L_menu,
                                pet=self.exp_pet, poke=self.exp_poke),
                   face=dict(pupil_small=pin, crest_deg=crest, fluff=fluff,
                             lid_droop=clamp(0.55 * e['sleepy'] + 0.2 * e['content'] + 0.15 * e['bored']
                                             + 0.3 * self.head_touch)),
                   gaze=dict(cursor_weight=look, saccade=bool(sacc)), blink=blink,
                   sounds=sounds, fx=fx, clip_events=list(self._clip_events),
                   follow=self._follow(e, look), petting=self._pet_out,
                   hand=dict(good=hg, bad=hb, sad=hs, touch_need=self.touch, neglect=self.neglect))
        self._changed = False
        self._pet_out = None
        self._sounds, self._fx, self._clip_events = [], [], []
        return out

    def _follow(self, e, look):
        """How the BODY should follow the cursor (the app turns / walks the bird; gaze is separate)."""
        cur, clip = self.cur, self.clip
        if cur in ('sleep', 'fly'):
            mode = 'none'
        elif cur == 'feed':
            mode = 'watch'
        elif cur in ('approach_hand', 'greet') or (cur == 'solicit_petting' and clip == 'walk_cycle') \
                or (cur == 'request_food' and clip == 'walk_to_screen'):
            mode = 'approach'
        elif cur in ('fear', 'avoid_hand', 'startle'):
            mode = 'avoid'
        elif cur == 'threaten':
            mode = 'confront'
        elif cur == 'mope' and (clip == 'sulk_turn_away' or self.x[self.fi['hand_sad']] > 0.3):
            mode = 'turn_away'
        elif look > 0.3:
            mode = 'watch'
        else:
            mode = 'idle'
        eager = clamp(0.4 * self.touch + 0.3 * self.social + 0.4 * e['excited'] + 0.3 * e['affectionate']
                      + 0.3 * e['hungry'] * self.present)
        return dict(mode=mode, walk=(mode == 'approach' and clip in ('walk_cycle', 'walk_to_screen')),
                    eagerness=eager, turn_deg_s=60.0 + 140.0 * self.A,
                    keep_px={'approach': 70, 'avoid': 260, 'confront': 120}.get(mode))

    # ------------------------------------------------------------------ persistence
    def get_state(self):
        return dict(version=5, saved_at=time.time(), hunger=self.hunger, S=self.S, social=self.social,
                    sleep_debt=self.sleep_debt,
                    boredom=self.boredom, groom=self.groom, stress=self.stress, mood=[self.mood_v, self.mood_a],
                    bond=self.bond, L_time=self.L_time.tolist(), L_menu=self.L_menu, exp_pet=self.exp_pet,
                    exp_poke=self.exp_poke, touch=self.touch, neglect=self.neglect, personality=self.P)

    def set_state(self, st, now=None, hour=None):
        """Restore, then fast-forward the body for the time the app was closed (user absent, max 24 h)."""
        for k in ('hunger', 'S', 'social', 'boredom', 'groom', 'stress', 'bond', 'L_menu', 'exp_pet', 'exp_poke'):
            setattr(self, k, float(st[k]))
        self.mood_v, self.mood_a = st['mood']
        self.L_time = np.array(st['L_time'])
        self.touch, self.neglect = float(st.get('touch', 0.35)), float(st.get('neglect', 0.0))
        self.sleep_debt = clamp(float(st.get('sleep_debt', 0.0)))
        gap = min(24 * 3600.0, max(0.0, (now or time.time()) - st.get('saved_at', time.time())))
        if hour is not None:
            self.hour = hour
        D = self.G.DRIVES
        self.hunger += (D['hunger_bowl'] - self.hunger) * (1 - math.exp(-gap / (D['hunger_rise_h'] * 3600)))
        self.social += (1 - self.social) * (1 - math.exp(-gap / (D['social_rise_min'] * 60 * 2)))
        self.boredom += (1 - self.boredom) * (1 - math.exp(-gap / (D['boredom_rise_min'] * 60 * 3)))
        self.S = clamp(self.S * math.exp(-gap / (D['sleep_fall_h'] * 3600)))
        self.sleep_debt *= math.exp(-gap / (self.G.SLEEP_DEBT['away_recover_h'] * 3600))   # it slept meanwhile
        self.touch += (1 - self.touch) * (1 - math.exp(-gap / (D['touch_rise_min'] * 60 * 1.5)))   # missed you
        self.neglect *= math.exp(-gap / (6 * 3600.0))      # being away is not ignoring; the reunion cheers it up
        self.mood_v *= math.exp(-gap / 86400.0)
        self.absent_s = gap
        return gap

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.get_state(), f, indent=1)

    def load(self, path, hour=None):
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return self.set_state(json.load(f), hour=hour)
        return None
